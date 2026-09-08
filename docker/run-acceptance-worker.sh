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
jobs_dir="${HARBOR_JOBS_DIR:-/tmp/papersmith-acceptance-jobs}"
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

mkdir -p "$jobs_dir"

if [[ "$enable" != 1 ]]; then
  echo "blocked: set HARBOR_RUN_ENABLED=1 to run real Harbor trials" >&2
  exit 2
fi

request_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["request_hash"])' "$request")"
task_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["task_id"])' "$request")"

run_trial() {
  local label="$1"
  local out="$jobs_dir/$label"
  rm -rf "$out"
  harbor run -p "$task_dir" --agent "$label" --jobs-dir "$out" --yes >/dev/null 2>&1
  python3 - "$out" "$label" <<'PY'
import json, sys
from pathlib import Path
jobs_dir, label = sys.argv[1], sys.argv[2]
result = sorted(Path(jobs_dir).glob("*/result.json"))[-1]
data = json.loads(result.read_text())
evals = data.get("stats", {}).get("evals", {})
trial = evals.get(f"{label}__adhoc", {})
reward_stats = trial.get("reward_stats", {}).get("reward", {})
if trial.get("n_errors", 0):
    raise SystemExit(f"{label} trial errored")
reward = float(next(iter(reward_stats)))
trial_id = next(iter(reward_stats.values()))[0]
print(f"{reward} {trial_id}")
PY
}

oracle_out="$(run_trial oracle)"
nop_out="$(run_trial nop)"
oracle_reward="${oracle_out%% *}"
oracle_trial="${oracle_out##* }"
nop_reward="${nop_out%% *}"
nop_trial="${nop_out##* }"

receipt_path="$(dirname "$request")/$(basename "$request" | sed 's/-request\.json$/-receipt.json/')"
python3 - "$receipt_path" "$request_hash" "$task_id" "$oracle_reward" "$oracle_trial" "$nop_reward" "$nop_trial" <<'PY'
import json, sys
receipt_path, request_hash, task_id = sys.argv[1], sys.argv[2], sys.argv[3]
oracle_reward, oracle_trial = float(sys.argv[4]), sys.argv[5]
nop_reward, nop_trial = float(sys.argv[6]), sys.argv[7]
receipt = {
    "worker": "papersmith-acceptance-worker",
    "request_hash": request_hash,
    "task_id": task_id,
    "trials": {
        "oracle": {"trial_id": oracle_trial, "reward": oracle_reward, "exit_status": 0},
        "nop": {"trial_id": nop_trial, "reward": nop_reward, "exit_status": 0},
    },
    "artifact_hashes": {"oracle_reward": oracle_reward, "nop_reward": nop_reward},
}
open(receipt_path, "w").write(json.dumps(receipt, indent=2) + "\n")
print(f"receipt written: {receipt_path} oracle={oracle_reward} nop={nop_reward}")
PY
