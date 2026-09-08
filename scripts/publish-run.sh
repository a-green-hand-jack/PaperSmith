#!/usr/bin/env bash
# Stage a validated run's accepted tasks into a HF config layout and upload.
set -euo pipefail

run_dir="${1:?usage: $0 <run-dir> [dataset] [config-dir] [prefix]}"
dataset="${2:-Jack-Jieke-Wu/Paper-Writing-Exam}"
config_dir="${3:-phys-paperrecon-short}"
prefix="${4:-pspr}"

test -f "$run_dir/delivery.json" || { echo "delivery.json not found; run validate first" >&2; exit 2; }

python3 - "$run_dir" "$config_dir" "$prefix" <<'PY'
import json, shutil, sys
from pathlib import Path
run_dir, config_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
delivery = json.load(open(Path(run_dir) / "delivery.json"))
accepted = [t for t in delivery["tasks"] if t.get("acceptance")]
if not accepted:
    raise SystemExit("no accepted tasks in delivery.json")
accepted.sort(key=lambda t: t["task_id"])
stage = Path("/tmp/hf-stage") / config_dir
stage.mkdir(parents=True, exist_ok=True)
entries = []
for i, t in enumerate(accepted, 1):
    tid = f"{prefix}-{i:04d}"
    src = Path(t["task_dir"])
    if not src.is_dir():
        raise SystemExit(f"task dir missing: {src}")
    dst = stage / tid
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    entries.append({
        "overview": "short",
        "task_id": tid,
        "upstream_paper_id": f"arXiv:{t['task_id']}",
        "upstream_revision": "v1",
    })
    print(f"staged {tid} <- {t['task_id']}")
manifest = stage / "dataset-manifest.jsonl"
with open(manifest, "w", encoding="utf-8") as f:
    for e in entries:
        f.write(json.dumps(e) + "\n")
print(f"wrote {manifest} ({len(entries)} entries)")
PY

hf upload "$dataset" "/tmp/hf-stage" --type dataset \
  --commit-message "Add $config_dir tasks ($(find /tmp/hf-stage/$config_dir -maxdepth 1 -mindepth 1 -type d | wc -l) tasks)"
