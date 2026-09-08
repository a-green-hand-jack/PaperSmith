#!/usr/bin/env bash
# Infrastructure smoke benchmark for PaperSmith. Backend: pi, and only pi.
#
# The emitted JSON record must name the provider and the credential source.
# Without those two fields a reader cannot tell a provider-backed run from an
# unauthenticated one, which makes the whole record worthless as evidence.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="${1:-papersmith}"
task_file="${2:-benchmarks/tasks/example-task.md}"
backend="${AGENT_BACKEND:-${PAPERSMITH_BACKEND:-pi}}"
provider="${LLM_PROVIDER:-}"
model="${LLM_MODEL:-}"
run_dir="${BENCHMARK_RUN_DIR:-$root/artifacts/benchmark-$(date +%Y%m%d-%H%M%S)}"
workspace="${BENCHMARK_WORKSPACE:-${E2E_WORKSPACE:-$run_dir/workspace}}"

case "$backend" in
  pi|pi-coding-agent) backend="pi" ;;
  *) echo "unsupported backend: $backend (this Agent supports pi only)" >&2; exit 2 ;;
esac
[[ -n "$provider" ]] || { echo "LLM_PROVIDER is required (never defaulted)" >&2; exit 2; }
[[ -n "$model" ]] || { echo "LLM_MODEL is required (never defaulted)" >&2; exit 2; }

mkdir -p "$workspace" "$workspace/artifacts"

task_prompt="$(sed '/^#/d; /^$/d' "$task_file" | tr '\n' ' ')"
trajectory="$run_dir/trajectory.jsonl"
scrubbed="$run_dir/trajectory.scrubbed.jsonl"
stderr_log="$run_dir/stderr.log"

export AGENT_OUTPUT_FORMAT=json

# Exactly one credential source, named explicitly so it can be recorded. The
# value is never read here.
credential_args=()
credential_source=""
if [[ -n "${BENCHMARK_API_KEY_ENV:-}" ]]; then
  [[ "$BENCHMARK_API_KEY_ENV" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
    echo "invalid BENCHMARK_API_KEY_ENV: $BENCHMARK_API_KEY_ENV" >&2; exit 2; }
  [[ -n "${!BENCHMARK_API_KEY_ENV:-}" ]] || {
    echo "BENCHMARK_API_KEY_ENV names an unset variable: $BENCHMARK_API_KEY_ENV" >&2; exit 2; }
  credential_args+=(--api-key-env "$BENCHMARK_API_KEY_ENV")
  credential_source="--api-key-env $BENCHMARK_API_KEY_ENV"
elif [[ -n "${PROVIDER_ENV_FILE:-}" ]]; then
  credential_args+=(--env-file "$PROVIDER_ENV_FILE")
  credential_source="--env-file $PROVIDER_ENV_FILE"
elif [[ -n "${PI_AUTH_FILE:-}" ]]; then
  credential_args+=(--pi-auth-file "$PI_AUTH_FILE")
  credential_source="--pi-auth-file $PI_AUTH_FILE"
fi
# A model catalog is a provider definition, not a credential.
[[ -n "${PI_MODELS_FILE:-}" ]] && credential_args+=(--pi-models-file "$PI_MODELS_FILE")

if [[ -z "$credential_source" ]]; then
  cat >&2 <<'EOF'
refusing to run: no credential source was named.

Set exactly one of:
  BENCHMARK_API_KEY_ENV=<HOST_VARIABLE>
  PROVIDER_ENV_FILE=<path from `accountctl docker-run --env-file-only --out`>
  PI_AUTH_FILE=<path to a read-only pi auth store>
EOF
  exit 2
fi

./docker/run-papersmith-e2e.sh --agent "$name" --backend "$backend" \
  --provider "$provider" --model "$model" \
  --workspace "$workspace" "${credential_args[@]}" "$task_prompt" \
  >"$trajectory" 2>"$stderr_log"

ARTIFACT_PATH="$workspace/artifacts/papersmith-smoke.md" \
  ./benchmarks/verifiers/example-verifier.sh
./scripts/collect-trace.sh "$trajectory" "$scrubbed" >/dev/null

version="$(./scripts/build-release.sh "$name" 0.1.0 >/dev/null 2>&1 && sed -n 's/.*"version":"\([^"]*\)".*/\1/p' "release/$name-0.1.0/release-manifest.json" || true)"
runtime_version="$(docker run --rm --entrypoint pi "$name:e2e" --version 2>/dev/null | tail -n 1)"
definition_revision="$(git rev-parse HEAD)+worktree-$(git diff --binary -- src/"$name" | sha256sum | cut -d' ' -f1)"

printf '{"benchmark":"papersmith-infrastructure-smoke","agent":"%s","backend":"%s","provider":"%s","model":"%s","credential_source":"%s","mode":"provider-backed","version":"%s","runtime":"%s","definition_revision":"%s","task":"%s","artifact":"%s","trajectory":"%s","scrubbed_trajectory":"%s"}\n' \
  "$name" "$backend" "$provider" "$model" "$credential_source" \
  "${version:-unknown}" "${runtime_version:-unknown}" "$definition_revision" \
  "$task_file" "$workspace/artifacts/papersmith-smoke.md" "$trajectory" "$scrubbed"
echo "evidence directory: $run_dir"
