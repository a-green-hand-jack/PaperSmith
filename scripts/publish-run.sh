#!/usr/bin/env bash
# Stage a validated run's accepted tasks into a HF config layout and upload.
#
# Task ids are allocated by continuing the dataset's existing numbering, under a
# lock, and the config manifest is appended to rather than rewritten. Restarting
# at 0001 per batch would silently overwrite previously published tasks, which is
# the failure mode that matters once more than one batch exists.
set -euo pipefail

run_dir="${1:?usage: $0 <run-dir> [dataset] [config-dir] [prefix]}"
dataset="${2:-Jack-Jieke-Wu/Paper-Writing-Exam}"
config_dir="${3:-phys-paperrecon-short}"
prefix="${4:-pspr}"

test -f "$run_dir/delivery.json" || { echo "delivery.json not found; run validate first" >&2; exit 2; }
command -v hf >/dev/null 2>&1 || { echo "hf CLI is required to publish" >&2; exit 2; }

stage_root="${HF_STAGE_DIR:-/tmp/hf-stage}"
lock_file="${PUBLISH_LOCK:-/tmp/papersmith-publish.lock}"

# Serialise publication: id allocation and the manifest append are a read-modify
# -write against shared state, so two concurrent batches must not interleave.
exec 9>"$lock_file"
flock 9

# The dataset is the authority on what numbers are taken. A missing manifest
# means this config is new, not that numbering starts over.
existing_manifest="$(mktemp -d)/dataset-manifest.jsonl"
trap 'rm -rf "$(dirname "$existing_manifest")"' EXIT
if hf download "$dataset" "$config_dir/dataset-manifest.jsonl" --repo-type dataset \
     --local-dir "$(dirname "$existing_manifest")/dl" >/dev/null 2>&1; then
  cp "$(dirname "$existing_manifest")/dl/$config_dir/dataset-manifest.jsonl" "$existing_manifest"
  echo "existing manifest: $(wc -l <"$existing_manifest") entry(ies) already published"
else
  : >"$existing_manifest"
  echo "no existing manifest for $config_dir; this is a new configuration"
fi

python3 - "$run_dir" "$config_dir" "$prefix" "$stage_root" "$existing_manifest" <<'PY'
import json, re, shutil, sys
from pathlib import Path

run_dir, config_dir, prefix, stage_root, existing_manifest = sys.argv[1:6]
delivery = json.load(open(Path(run_dir) / "delivery.json"))
accepted = [t for t in delivery["tasks"] if t.get("acceptance")]
if not accepted:
    raise SystemExit("no accepted tasks in delivery.json")
accepted.sort(key=lambda t: t["task_id"])

# Continue the existing numbering rather than restarting it.
published = []
taken = set()
highest = 0
for line in Path(existing_manifest).read_text(encoding="utf-8", errors="replace").splitlines():
    if not line.strip():
        continue
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        continue
    published.append(record)
    task_id = str(record.get("task_id") or "")
    taken.add(task_id)
    match = re.fullmatch(re.escape(prefix) + r"-(\d+)", task_id)
    if match:
        highest = max(highest, int(match.group(1)))

stage = Path(stage_root) / config_dir
stage.mkdir(parents=True, exist_ok=True)

next_index = highest
entries = []
for task in accepted:
    upstream = str(task["task_id"])
    # task_id already carries its scheme (e.g. "arXiv:2601.02265"); prefixing it
    # again produced "arXiv:arXiv:..." in the published manifest.
    if not re.match(r"^[A-Za-z]+:", upstream):
        upstream = f"arXiv:{upstream}"
    next_index += 1
    tid = f"{prefix}-{next_index:04d}"
    while tid in taken:
        next_index += 1
        tid = f"{prefix}-{next_index:04d}"
    source = Path(task["task_dir"])
    if not source.is_dir():
        raise SystemExit(f"task dir missing: {source}")
    destination = stage / tid
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(source, destination)
    entries.append(
        {
            "overview": "short",
            "task_id": tid,
            "upstream_paper_id": upstream,
            "upstream_revision": "v1",
        }
    )
    taken.add(tid)
    print(f"staged {tid} <- {upstream}")

manifest = stage / "dataset-manifest.jsonl"
with open(manifest, "w", encoding="utf-8") as handle:
    for record in published + entries:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
print(f"wrote {manifest} ({len(published)} existing + {len(entries)} new)")
PY

new_tasks="$(find "$stage_root/$config_dir" -maxdepth 1 -mindepth 1 -type d | wc -l)"
hf upload "$dataset" "$stage_root" --type dataset \
  --commit-message "Add $config_dir tasks ($new_tasks tasks)"
