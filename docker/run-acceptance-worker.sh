#!/usr/bin/env bash
# Trusted host acceptance worker for PaperSmith.
#
# Runs REAL Harbor oracle/nop trials for an acceptance request and writes an
# immutable, hash-bound receipt. This runs on the host (outside the control
# container); the producing/writing agent never gets Docker or Harbor control.
#
# Fails closed unless Harbor and a runnable task verifier are present. Rewards
# are read back from Harbor job results, never assumed.
set -euo pipefail

request="${1:?usage: $0 <acceptance-request.json>}"
jobs_root="${HARBOR_JOBS_DIR:-/tmp/papersmith-acceptance-jobs}"
enable="${HARBOR_RUN_ENABLED:-1}"

test -f "$request" || { echo "acceptance request not found: $request" >&2; exit 2; }
command -v harbor >/dev/null 2>&1 || { echo "harbor CLI is not installed on the host" >&2; exit 2; }

task_dir="$(python3 - "$request" <<'PY'
import json, os, sys
from pathlib import Path
request_path = sys.argv[1]
req = json.load(open(request_path))
for key in ("task_id", "task_dir", "manifest", "oracle", "request_hash"):
    assert key in req, f"request missing {key}"
task_dir = req["task_dir"]
if not os.path.isdir(task_dir):
    run_root = Path(request_path).resolve().parent.parent
    slug = req["task_id"].replace("/", "_").replace(":", "_")
    matches = [p for p in (run_root / "tasks").iterdir() if p.is_dir() and slug in p.name] \
        if (run_root / "tasks").is_dir() else []
    if matches:
        task_dir = str(matches[0])
    else:
        raise AssertionError(f"cannot resolve task_dir: {req['task_dir']}")
for rel in ("task.toml", "instruction.md", "tests/test.sh", "tests/test_state.py",
            "tests/grader_pwb.py", "solution/solve.sh", "solution/normalize.py",
            "solution/private/main.tex", "environment/Dockerfile"):
    assert os.path.isfile(os.path.join(task_dir, rel)), f"task missing {rel}"
print(task_dir)
PY
)"


if [[ "$enable" != 1 ]]; then
  echo "blocked: set HARBOR_RUN_ENABLED=1 to run real Harbor trials" >&2
  exit 2
fi

request_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["request_hash"])' "$request")"
task_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["task_id"])' "$request")"

# One jobs directory per task. A shared path combined with the per-trial
# `rm -rf` below let concurrent acceptance workers delete each other's Harbor
# job output, which batch acceptance does by design.
task_slug="$(printf '%s' "$task_id" | tr -c 'A-Za-z0-9._-' '_')"
jobs_dir="$jobs_root/$task_slug"
mkdir -p "$jobs_dir"

receipt_path="$(dirname "$request")/$(basename "$request" | sed 's/-request\.json$/-receipt.json/')"
# Check we can actually write the receipt BEFORE paying for two Harbor trials.
# A run directory created inside the container is owned by root, so a host
# worker silently loses the evidence at the very end without this.
if ! : >>"$receipt_path" 2>/dev/null; then
  echo "cannot write the receipt: $receipt_path" >&2
  echo "the run directory is probably owned by another user (the control container runs as root)." >&2
  echo "fix ownership first, e.g.:" >&2
  echo "  docker run --rm --entrypoint chmod -v \"\$(dirname \"$(dirname "$request")\"):/run\" <image> -R a+rwX /run" >&2
  exit 2
fi

run_trial() {
  local label="$1"
  local out="$jobs_dir/$label"
  local log="$jobs_dir/$label.harbor.log"
  rm -rf "$out"
  # Record the real exit status instead of asserting success, and keep the log:
  # a discarded log makes a failure in a 300-task batch undiagnosable.
  local status=0
  harbor run -p "$task_dir" --agent "$label" --jobs-dir "$out" --yes >"$log" 2>&1 || status=$?
  if [[ "$status" -ne 0 ]]; then
    echo "harbor $label trial exited $status; see $log" >&2
  fi
  python3 - "$out" "$label" "$status" <<'PY'
import json, sys
from pathlib import Path
jobs_dir, label, exit_status = sys.argv[1], sys.argv[2], sys.argv[3]
results = sorted(Path(jobs_dir).glob("*/result.json"))
if not results:
    raise SystemExit(f"{label} trial produced no result.json under {jobs_dir}")
result = results[-1]
data = json.loads(result.read_text())
evals = data.get("stats", {}).get("evals", {})
trial = evals.get(f"{label}__adhoc", {})
reward_stats = trial.get("reward_stats", {}).get("reward", {})
if trial.get("n_errors", 0):
    raise SystemExit(f"{label} trial errored")
reward = float(next(iter(reward_stats)))
trial_id = next(iter(reward_stats.values()))[0]
print(f"{reward} {trial_id} {exit_status}")
PY
}

oracle_out="$(run_trial oracle)"
nop_out="$(run_trial nop)"
read -r oracle_reward oracle_trial oracle_status <<<"$oracle_out"
read -r nop_reward nop_trial nop_status <<<"$nop_out"

python3 - "$receipt_path" "$request_hash" "$task_id" "$oracle_reward" "$oracle_trial" "$oracle_status" "$nop_reward" "$nop_trial" "$nop_status" <<'PY'
import json, sys
receipt_path, request_hash, task_id = sys.argv[1], sys.argv[2], sys.argv[3]
oracle_reward, oracle_trial, oracle_status = float(sys.argv[4]), sys.argv[5], int(sys.argv[6])
nop_reward, nop_trial, nop_status = float(sys.argv[7]), sys.argv[8], int(sys.argv[9])
receipt = {
    "worker": "papersmith-acceptance-worker",
    "request_hash": request_hash,
    "task_id": task_id,
    "trials": {
        "oracle": {"trial_id": oracle_trial, "reward": oracle_reward, "exit_status": oracle_status},
        "nop": {"trial_id": nop_trial, "reward": nop_reward, "exit_status": nop_status},
    },
    "artifact_hashes": {"oracle_reward": oracle_reward, "nop_reward": nop_reward},
}
open(receipt_path, "w").write(json.dumps(receipt, indent=2) + "\n")
print(f"receipt written: {receipt_path} oracle={oracle_reward} nop={nop_reward}")
PY
