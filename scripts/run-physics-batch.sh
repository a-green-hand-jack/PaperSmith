#!/usr/bin/env bash
# One-process PaperSmith physics batch: build -> create (discovery) -> accept -> publish.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

COUNT="${1:-20}"
RUN_DIR="${2:-/tmp/phys-run}"
IMAGE="papersmith:e2e"
AUTH_FILE="${OPENCODE_AUTH_FILE:-$HOME/.local/share/opencode/auth.json}"
PROVIDER="${LLM_PROVIDER:-opencode-go}"
MODEL="${LLM_MODEL:-deepseek-v4-flash}"
REVIEW_MODEL="${LLM_REVIEW_MODEL:-deepseek-v4-flash}"

echo "=== 1/4 build image ==="
docker build -t "$IMAGE" -f docker/Dockerfile . > /tmp/phys-batch-build.log 2>&1

echo "=== 2/4 create (discovery, $COUNT physics tasks) ==="
rm -rf "$RUN_DIR" && mkdir -p "$RUN_DIR"
docker run --rm -e AGENT_AUTH_STORE=1 \
  -v "$AUTH_FILE:/root/.local/share/opencode/auth.json:ro" \
  -v "$RUN_DIR:/tmp/run" "$IMAGE" \
  papersmith create 'discover and reconstruct physics research papers' \
    --selection discovery --domain physics --count "$COUNT" --output /tmp/run \
    --backend opencode --provider "$PROVIDER" --model "$MODEL" --review-model "$REVIEW_MODEL" \
  > /tmp/phys-create-result.json 2>&1 || { echo "create failed" >&2; tail -30 /tmp/phys-create-result.json; exit 1; }

docker run --rm --entrypoint chmod -v "$RUN_DIR:/tmp/run" "$IMAGE" -R a+rwX /tmp/run >/dev/null
python3 -c "import json; d=json.load(open('/tmp/phys-create-result.json')); print('create ok:', d.get('ok'), 'tasks:', len(d.get('tasks',[])), 'considered:', d.get('candidates_considered'))"

echo "=== 3/4 accept + validate ==="
"$root/scripts/accept-run.sh" "$RUN_DIR" "$IMAGE"

echo "=== 4/4 publish to HF (phys-paperrecon-short) ==="
"$root/scripts/publish-run.sh" "$RUN_DIR" "Jack-Jieke-Wu/Paper-Writing-Exam" "phys-paperrecon-short" "pspr"

echo "=== DONE ==="
