#!/usr/bin/env bash
# Single-shard PaperSmith batch: build -> create -> accept -> publish.
# Backend: pi, and only pi.
#
# Credentials are injected through accountctl, which is the single approved
# entry point. Note that `accountctl docker-run` cannot pass docker flags or
# mount anything, so it is used here as an env-file producer and the container
# is started by this script, which needs to mount the run directory.
#
# This is the serial, single-domain path. The parallel multi-domain driver
# supersedes it; keep this one as the smallest reproducible batch.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

COUNT="${1:-20}"
RUN_DIR="${2:-/tmp/phys-run}"
DOMAIN="${DOMAIN:-physics}"
IMAGE="papersmith:e2e"
PROVIDER="${LLM_PROVIDER:-gravarc-router}"
MODEL="${LLM_MODEL:-kimi-k3}"
REVIEW_MODEL="${LLM_REVIEW_MODEL:-$MODEL}"
ACCOUNT="${PROVIDER_ACCOUNT:-$PROVIDER}"
CONFIG_DIR="${CONFIG_DIR:-phys-paperrecon-short}"
PREFIX="${TASK_PREFIX:-pspr}"

# pi resolves a custom provider from its own catalog. In a container the catalog
# must carry an env-var reference for the key, never the key itself.
PI_MODELS_FILE="${PI_MODELS_FILE:-}"
if [[ -z "$PI_MODELS_FILE" ]]; then
  PI_MODELS_FILE="$(mktemp /tmp/pi-models-container.XXXXXX.json)"
  python3 - "$HOME/.pi/agent/models.json" "$PROVIDER" "$PI_MODELS_FILE" <<'PY'
import json, re, sys
source, provider, dest = sys.argv[1], sys.argv[2], sys.argv[3]
catalog = json.load(open(source))
entry = (catalog.get("providers") or {}).get(provider)
if entry is None:
    raise SystemExit(f"provider {provider!r} is not defined in {source}")
env_name = re.sub(r"[^A-Za-z0-9]", "_", provider).upper() + "_API_KEY"
entry = dict(entry)
entry["apiKey"] = f"${env_name}"
json.dump({"providers": {provider: entry}}, open(dest, "w"), indent=2)
print(f"containerized catalog for {provider} -> {dest} (apiKey references ${env_name})")
PY
fi

ENV_FILE="${PROVIDER_ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="/run/user/$(id -u)/papersmith-providers.$$.env"
  accountctl docker-run --providers "$ACCOUNT" --env-file-only --out "$ENV_FILE"
  trap 'rm -f "$ENV_FILE"' EXIT
fi

echo "=== 1/4 build image ==="
docker build --build-arg AGENT_NAME=papersmith -t "$IMAGE" -f docker/Dockerfile . > /tmp/batch-build.log 2>&1

echo "=== 2/4 create (discovery, $COUNT $DOMAIN tasks) ==="
rm -rf "$RUN_DIR" && mkdir -p "$RUN_DIR"
docker run --rm \
  --env-file "$ENV_FILE" \
  --env "AGENT_BACKEND=pi" \
  --env "LLM_PROVIDER=$PROVIDER" --env "LLM_MODEL=$MODEL" --env "LLM_REVIEW_MODEL=$REVIEW_MODEL" \
  --env "PI_CODING_AGENT_DIR=/root/.pi/agent" \
  ${BOHR_ACCESS_KEY:+--env "BOHR_ACCESS_KEY=$BOHR_ACCESS_KEY"} \
  --mount "type=bind,src=$(realpath "$PI_MODELS_FILE"),dst=/root/.pi/agent/models.json,readonly" \
  -v "$RUN_DIR:/tmp/run" "$IMAGE" \
  papersmith create "discover and reconstruct $DOMAIN research papers" \
    --selection discovery --domain "$DOMAIN" --count "$COUNT" --output /tmp/run \
    --backend pi --provider "$PROVIDER" --model "$MODEL" --review-model "$REVIEW_MODEL" \
  > /tmp/batch-create-result.json 2>&1 || { echo "create failed" >&2; tail -30 /tmp/batch-create-result.json; exit 1; }

docker run --rm --entrypoint chmod -v "$RUN_DIR:/tmp/run" "$IMAGE" -R a+rwX /tmp/run >/dev/null
python3 -c "import json; d=json.load(open('/tmp/batch-create-result.json')); print('create ok:', d.get('ok'), 'tasks:', len(d.get('tasks',[])), 'considered:', d.get('candidates_considered'))"

echo "=== 3/4 accept + validate ==="
"$root/scripts/accept-run.sh" "$RUN_DIR" "$IMAGE"

echo "=== 4/4 publish to HF ($CONFIG_DIR) ==="
"$root/scripts/publish-run.sh" "$RUN_DIR" "Jack-Jieke-Wu/Paper-Writing-Exam" "$CONFIG_DIR" "$PREFIX"

echo "=== DONE ==="
