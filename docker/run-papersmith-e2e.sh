#!/usr/bin/env bash
# Provider-backed Docker E2E for PaperSmith. Backend: pi, and only pi.
#
# Fails closed. A task run with no injected credential is refused, because an
# unauthenticated run is indistinguishable from a provider-backed one in the
# evidence record — which is exactly the confusion this harness exists to
# prevent. Use --allow-unauthenticated only for an infrastructure-only smoke
# (build, --help, doctor); such a run is reported as infrastructure-only and is
# never Agent-behavior evidence.
#
# Provider and model are injected, never defaulted: this Agent is LLM-agnostic
# and the harness must not silently pick one.
set -euo pipefail
name="${AGENT_NAME:-papersmith}"
backend="${AGENT_BACKEND:-${PAPERSMITH_BACKEND:-pi}}"
provider="${LLM_PROVIDER:-}"
model="${LLM_MODEL:-}"
api_key_env=""
api_key_stdin=false
env_file="${ENV_FILE:-.env}"
env_file_explicit=false
bundle=""
workspace="${E2E_WORKSPACE:-}"
pi_auth_file="${PI_AUTH_FILE:-}"
pi_models_file="${PI_MODELS_FILE:-}"
no_build=false
allow_unauthenticated=false

usage() {
  printf '%s\n' "Usage: $0 [options] <task>" "" \
    "Backend: pi, and only pi." "" \
    "Options:" \
    "  --provider NAME       Provider name (required; never defaulted)" \
    "  --model NAME          Model name (required; never defaulted)" \
    "  --api-key-env NAME    Read the provider key from this host variable" \
    "  --api-key-stdin       Read the provider key from stdin (never shell history)" \
    "  --env-file PATH       Load variables from PATH (e.g. accountctl output)" \
    "  --bundle PATH         Mount a read-only provider bundle" \
    "  --pi-auth-file PATH   Mount one pi auth store read-only" \
    "  --pi-models-file PATH Mount one pi model catalog read-only" \
    "  --workspace PATH      Mount PATH as the clean container workspace" \
    "  --no-build            Reuse the existing image for this Agent" \
    "  --agent NAME          Build and run a different src/<agent>" \
    "  --allow-unauthenticated  Infrastructure-only smoke; NOT behavior evidence" \
    "  -h, --help            Show this help" "" \
    "Produce an env file with:" \
    "  accountctl docker-run --providers <account> --env-file-only --out <path>"
}

while (($#)); do
  case "$1" in
    --backend) backend="${2:?missing value for --backend}"; shift 2 ;;
    --provider) provider="${2:?missing value for --provider}"; shift 2 ;;
    --model) model="${2:?missing value for --model}"; shift 2 ;;
    --api-key-env) api_key_env="${2:?missing value for --api-key-env}"; shift 2 ;;
    --api-key-stdin) api_key_stdin=true; shift ;;
    --env-file) env_file="${2:?missing value for --env-file}"; env_file_explicit=true; shift 2 ;;
    --bundle) bundle="${2:?missing value for --bundle}"; shift 2 ;;
    --pi-auth-file) pi_auth_file="${2:?missing value for --pi-auth-file}"; shift 2 ;;
    --pi-models-file) pi_models_file="${2:?missing value for --pi-models-file}"; shift 2 ;;
    --workspace) workspace="${2:?missing value for --workspace}"; shift 2 ;;
    --no-build) no_build=true; shift ;;
    --agent) name="${2:?missing value for --agent}"; shift 2 ;;
    --allow-unauthenticated) allow_unauthenticated=true; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) printf 'unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *) break ;;
  esac
done

case "$backend" in
  pi|pi-coding-agent) backend="pi" ;;
  *) printf 'unsupported backend: %s (this Agent supports pi only)\n' "$backend" >&2; exit 2 ;;
esac

task=()
while (($#)); do task+=("$1"); shift; done
if ((${#task[@]} == 0)); then usage >&2; exit 2; fi

if [[ "$allow_unauthenticated" != true ]]; then
  [[ -n "$provider" ]] || { echo "--provider or LLM_PROVIDER is required (never defaulted)" >&2; exit 2; }
  [[ -n "$model" ]] || { echo "--model or LLM_MODEL is required (never defaulted)" >&2; exit 2; }
fi
provider_key_prefix="$(printf '%s' "$provider" | tr '[:lower:]-.' '[:upper:]__')"
key_variable="${provider_key_prefix}_API_KEY"

env_args=(--env "AGENT_BACKEND=$backend")
[[ -n "$provider" ]] && env_args+=(--env "LLM_PROVIDER=$provider")
[[ -n "$model" ]] && env_args+=(--env "LLM_MODEL=$model")
[[ -n "${LLM_REVIEW_MODEL:-}" ]] && env_args+=(--env "LLM_REVIEW_MODEL=$LLM_REVIEW_MODEL")
[[ -n "${AGENT_OUTPUT_FORMAT:-}" ]] && env_args+=(--env "AGENT_OUTPUT_FORMAT=$AGENT_OUTPUT_FORMAT")

# ---------------------------------------------------------------------------
# Credential resolution. Exactly one source is recorded, and the value is never
# printed. `credential_source` becomes part of the evidence line below.
# ---------------------------------------------------------------------------
credential_source=""
if [[ -n "$api_key_env" ]]; then
  [[ -n "${!api_key_env:-}" ]] || { printf '%s is not set\n' "$api_key_env" >&2; exit 2; }
  [[ -n "$provider" ]] || { echo "--api-key-env requires a provider" >&2; exit 2; }
  env_args+=(--env "$key_variable=${!api_key_env}")
  credential_source="--api-key-env $api_key_env"
elif [[ "$api_key_stdin" == true ]]; then
  IFS= read -r api_key
  [[ -n "$api_key" ]] || { printf 'provider key from stdin is empty\n' >&2; exit 2; }
  [[ -n "$provider" ]] || { echo "--api-key-stdin requires a provider" >&2; exit 2; }
  env_args+=(--env "$key_variable=$api_key")
  credential_source="--api-key-stdin"
  unset api_key
fi

env_file_args=()
if [[ -f "$env_file" ]]; then
  env_file_args=(--env-file "$env_file")
  # An env file only counts as a credential source when it actually carries a
  # non-empty provider key; otherwise fail-closed would be trivially bypassed
  # by the default .env being present.
  if [[ -z "$credential_source" ]] && grep -Eq "^${key_variable}=.+" "$env_file" 2>/dev/null; then
    credential_source="--env-file $env_file"
  fi
elif [[ "$env_file_explicit" == true ]]; then
  echo "env file does not exist: $env_file" >&2
  exit 2
fi

bundle_args=()
if [[ -n "$bundle" ]]; then
  [[ -f "$bundle/manifest.json" && -f "$bundle/credential" ]] || { echo "invalid provider bundle" >&2; exit 2; }
  bundle_key_env="$(sed -n 's/.*"credential_env":"\([A-Za-z_][A-Za-z0-9_]*\)".*/\1/p' "$bundle/manifest.json")"
  [[ -n "$bundle_key_env" ]] || { echo "invalid provider bundle manifest" >&2; exit 2; }
  env_args+=(--env "$bundle_key_env=$(<"$bundle/credential")")
  bundle_args=(--mount "type=bind,src=$(realpath "$bundle"),dst=/run/provider-bundle,readonly")
  [[ -n "$credential_source" ]] || credential_source="--bundle $bundle"
fi

pi_auth_args=()
if [[ -n "$pi_auth_file" ]]; then
  [[ -f "$pi_auth_file" ]] || { echo "pi auth file does not exist: $pi_auth_file" >&2; exit 2; }
  pi_auth_args=(--env PI_AUTH_STORE=1 --env PI_CODING_AGENT_DIR=/root/.pi/agent
    --mount "type=bind,src=$(realpath "$pi_auth_file"),dst=/root/.pi/agent/auth.json,readonly")
  [[ -n "$credential_source" ]] || credential_source="--pi-auth-file $pi_auth_file"
  if [[ -z "$pi_models_file" ]]; then
    candidate_models_file="$(dirname "$pi_auth_file")/models.json"
    [[ -f "$candidate_models_file" ]] && pi_models_file="$candidate_models_file"
  fi
fi
# A model catalog is a provider definition, not a credential: it may be mounted
# on its own, and it does not satisfy the fail-closed check.
if [[ -n "$pi_models_file" ]]; then
  [[ -f "$pi_models_file" ]] || { echo "pi models file does not exist: $pi_models_file" >&2; exit 2; }
  pi_auth_args+=(--env PI_CODING_AGENT_DIR=/root/.pi/agent
    --mount "type=bind,src=$(realpath "$pi_models_file"),dst=/root/.pi/agent/models.json,readonly")
fi

# Last resort: the provider key already present in this shell.
if [[ -z "$credential_source" && -n "$provider" && -n "${!key_variable:-}" ]]; then
  env_args+=(--env "$key_variable=${!key_variable}")
  credential_source="host env $key_variable"
fi

mode="provider-backed"
if [[ -z "$credential_source" ]]; then
  if [[ "$allow_unauthenticated" != true ]]; then
    cat >&2 <<EOF
refusing to run: no provider credential was injected.

Inject exactly one of:
  --api-key-env NAME          read the key from a host variable
  --api-key-stdin             read the key from stdin
  --env-file PATH             an env file carrying $key_variable
                              (accountctl docker-run --providers <account> \\
                                 --env-file-only --out PATH)
  --bundle PATH               a provider bundle directory
  --pi-auth-file PATH         a read-only pi auth store
  export $key_variable        already set in this shell

Or pass --allow-unauthenticated for an infrastructure-only smoke. That run is
reported as infrastructure-only and is NOT Agent-behavior evidence.
EOF
    exit 2
  fi
  mode="infrastructure-only"
  credential_source="none"
fi

# Domain tool credential for the bohr CLI (Bohrium LKM depth, PDF text). Not a
# backend and not an LLM provider, so it never satisfies the credential gate.
for passthrough_env in BOHR_ACCESS_KEY OPENAI_BASE_URL ANTHROPIC_BASE_URL; do
  if [[ -n "${!passthrough_env:-}" ]]; then
    env_args+=(--env "$passthrough_env=${!passthrough_env}")
  fi
done

workspace_args=()
if [[ -n "$workspace" ]]; then
  [[ -d "$workspace" ]] || { echo "workspace directory does not exist: $workspace" >&2; exit 2; }
  workspace_args=(--mount "type=bind,src=$(realpath "$workspace"),dst=/workspace")
fi

if [[ "$no_build" != true ]]; then
  docker build --build-arg AGENT_NAME="$name" -t "$name:e2e" -f docker/Dockerfile . >&2
fi

printf 'papersmith-e2e: agent=%s backend=%s provider=%s model=%s credential_source=%s mode=%s\n' \
  "$name" "$backend" "${provider:-none}" "${model:-none}" "$credential_source" "$mode" >&2

tty_args=()
if [[ -t 0 && -t 1 ]]; then
  tty_args=(-it)
fi
docker run --rm "${tty_args[@]}" "${env_file_args[@]}" "${env_args[@]}" "${bundle_args[@]}" \
  "${workspace_args[@]}" "${pi_auth_args[@]}" "$name:e2e" "${task[@]}"
