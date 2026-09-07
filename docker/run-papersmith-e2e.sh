#!/usr/bin/env bash
set -euo pipefail
name="${AGENT_NAME:-papersmith}"
backend="${AGENT_BACKEND:-${PAPERSMITH_BACKEND:-opencode}}"
provider="${LLM_PROVIDER:-}"
model="${LLM_MODEL:-}"
api_key_env=""
workspace="${E2E_WORKSPACE:-}"
auth_file="${OPENCODE_AUTH_FILE:-}"
codex_auth_file="${CODEX_AUTH_FILE:-}"
claude_credentials_file="${CLAUDE_CREDENTIALS_FILE:-}"
claude_api_key_file="${CLAUDE_API_KEY_FILE:-}"
codex_sandbox_mode="${CODEX_SANDBOX_MODE:-workspace-write}"
no_build=false

usage() {
  printf '%s\n' "Usage: $0 [options] <task>" "" \
    "Options:" \
    "  --backend NAME       Backend: opencode, codex, or claude" \
    "  --provider NAME       OpenCode provider name (backend-specific default)" \
    "  --model NAME          Model name (backend-specific default)" \
    "  --api-key-env NAME    Forward the selected backend key variable from the host" \
    "  --auth-file PATH      Mount one explicit OpenCode auth store read-only" \
    "  --codex-auth-file PATH Mount one explicit Codex auth store read-only" \
    "  --claude-credentials-file PATH Mount Claude credentials read-only" \
    "  --claude-api-key-file PATH Mount one Claude API key file read-only" \
    "  --codex-sandbox-mode MODE Codex sandbox: read-only, workspace-write, or danger-full-access" \
    "  --workspace PATH      Mount PATH as the clean container workspace" \
    "  --no-build            Reuse the existing image for this Agent" \
    "  --agent NAME          Build and run a different src/<agent>" \
    "  -h, --help            Show this help"
}

while (($#)); do
  case "$1" in
    --backend) backend="${2:?missing value for --backend}"; shift 2 ;;
    --provider) provider="${2:?missing value for --provider}"; shift 2 ;;
    --model) model="${2:?missing value for --model}"; shift 2 ;;
    --api-key-env) api_key_env="${2:?missing value for --api-key-env}"; shift 2 ;;
    --auth-file) auth_file="${2:?missing value for --auth-file}"; shift 2 ;;
    --codex-auth-file) codex_auth_file="${2:?missing value for --codex-auth-file}"; shift 2 ;;
    --claude-credentials-file) claude_credentials_file="${2:?missing value for --claude-credentials-file}"; shift 2 ;;
    --claude-api-key-file) claude_api_key_file="${2:?missing value for --claude-api-key-file}"; shift 2 ;;
    --codex-sandbox-mode) codex_sandbox_mode="${2:?missing value for --codex-sandbox-mode}"; shift 2 ;;
    --workspace) workspace="${2:?missing value for --workspace}"; shift 2 ;;
    --no-build) no_build=true; shift ;;
    --agent) name="${2:?missing value for --agent}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) printf 'unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *) break ;;
  esac
done

case "$backend" in
  open-code) backend="opencode" ;;
  claude-code) backend="claude" ;;
esac
if [[ "$backend" == opencode && -z "$provider" && "$model" == */* ]]; then
  provider="${model%%/*}"
  model="${model#*/}"
fi
case "$backend" in
  opencode) [[ -n "$provider" ]] || { echo "--provider is required for OpenCode E2E" >&2; exit 2; } ;;
  codex) provider="codex" ;;
  claude) provider="claude" ;;
  *) echo "unsupported backend: $backend (expected opencode, codex, or claude)" >&2; exit 2 ;;
esac
provider_key_prefix="$(printf '%s' "$provider" | tr '[:lower:]-.' '[:upper:]__')"
[[ -n "$model" ]] || { echo "--model is required for provider-backed E2E" >&2; exit 2; }

task=()
while (($#)); do task+=("$1"); shift; done
if ((${#task[@]} == 0)); then usage >&2; exit 2; fi

if [[ "$no_build" != true ]]; then
  docker build --build-arg AGENT_NAME="$name" -t "$name:e2e" -f docker/Dockerfile . >&2
fi
env_args=()
env_args+=(--env "AGENT_BACKEND=$backend" --env "LLM_PROVIDER=$provider" --env "LLM_MODEL=$model" --env "CODEX_SANDBOX_MODE=$codex_sandbox_mode")
if [[ -n "${LLM_VARIANT:-}" ]]; then
  env_args+=(--env "LLM_VARIANT=$LLM_VARIANT")
fi
if [[ -n "${AGENT_OUTPUT_FORMAT:-}" ]]; then
  env_args+=(--env "AGENT_OUTPUT_FORMAT=$AGENT_OUTPUT_FORMAT")
fi
key_variable="${provider_key_prefix}_API_KEY"
[[ "$backend" == codex ]] && key_variable=OPENAI_API_KEY
[[ "$backend" == claude ]] && key_variable=ANTHROPIC_API_KEY
if [[ -n "$api_key_env" && "$api_key_env" != "$key_variable" ]]; then
  echo "--api-key-env must match the selected backend key variable: $key_variable" >&2
  exit 2
fi
if [[ -n "${!key_variable:-}" ]]; then
  env_args+=(--env "$key_variable")
fi

passthrough_envs=()
case "$backend" in
  opencode) passthrough_envs=("${provider_key_prefix}_BASE_URL") ;;
  codex) passthrough_envs=(OPENAI_BASE_URL) ;;
  claude) passthrough_envs=(ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN) ;;
esac
for passthrough_env in "${passthrough_envs[@]}"; do
  if [[ -n "${!passthrough_env:-}" ]]; then
    env_args+=(--env "$passthrough_env=${!passthrough_env}")
  fi
done

case "$backend" in
  opencode)
    [[ -z "$codex_auth_file" && -z "$claude_credentials_file" && -z "$claude_api_key_file" ]] || {
      echo "credential option does not match selected OpenCode backend" >&2
      exit 2
    }
    ;;
  codex)
    [[ -z "$auth_file" && -z "$claude_credentials_file" && -z "$claude_api_key_file" ]] || {
      echo "credential option does not match selected Codex backend" >&2
      exit 2
    }
    ;;
  claude)
    [[ -z "$auth_file" && -z "$codex_auth_file" ]] || {
      echo "credential option does not match selected Claude backend" >&2
      exit 2
    }
    ;;
esac

workspace_args=()
if [[ -n "$workspace" ]]; then
  [[ -d "$workspace" ]] || { echo "workspace directory does not exist: $workspace" >&2; exit 2; }
  workspace_args=(--mount "type=bind,src=$(realpath "$workspace"),dst=/workspace")
fi

auth_args=()
if [[ -n "$auth_file" ]]; then
  [[ -f "$auth_file" ]] || { echo "auth file does not exist: $auth_file" >&2; exit 2; }
  auth_args=(--env AGENT_AUTH_STORE=1 --mount "type=bind,src=$(realpath "$auth_file"),dst=/root/.local/share/opencode/auth.json,readonly")
fi

codex_auth_args=()
if [[ -n "$codex_auth_file" ]]; then
  [[ -f "$codex_auth_file" ]] || { echo "Codex auth file does not exist: $codex_auth_file" >&2; exit 2; }
  codex_auth_args=(--env CODEX_AUTH_STORE=1 --env CODEX_HOME=/root/.codex --mount "type=bind,src=$(realpath "$codex_auth_file"),dst=/root/.codex/auth.json,readonly")
fi

claude_auth_args=()
if [[ -n "$claude_credentials_file" ]]; then
  [[ -f "$claude_credentials_file" ]] || { echo "Claude credentials file does not exist: $claude_credentials_file" >&2; exit 2; }
  claude_auth_args=(--env CLAUDE_AUTH_STORE=1 --env CLAUDE_CONFIG_DIR=/root/.claude --mount "type=bind,src=$(realpath "$claude_credentials_file"),dst=/root/.claude/.credentials.json,readonly")
fi
if [[ -n "$claude_api_key_file" ]]; then
  [[ -f "$claude_api_key_file" ]] || { echo "Claude API key file does not exist: $claude_api_key_file" >&2; exit 2; }
  claude_auth_args+=(--env ANTHROPIC_API_KEY_FILE=/run/secrets/anthropic_api_key --mount "type=bind,src=$(realpath "$claude_api_key_file"),dst=/run/secrets/anthropic_api_key,readonly")
fi

tty_args=()
if [[ -t 0 && -t 1 ]]; then
  tty_args=(-it)
fi
docker run --rm "${tty_args[@]}" "${env_args[@]}" "${workspace_args[@]}" "${auth_args[@]}" "${codex_auth_args[@]}" "${claude_auth_args[@]}" "$name:e2e" "${task[@]}"
