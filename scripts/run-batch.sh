#!/usr/bin/env bash
# Parallel PaperSmith batch driver. Backend: pi, and only pi.
#
# Three stages, each independently re-runnable:
#
#   create   N containers in parallel, one per domain shard. Shards partition
#            the submission window, so workers never chase the same paper, and
#            a shared ledger catches the cross-listed ones that slip through.
#   accept   Real Harbor oracle/nop trials on the host, bounded in parallel.
#            Each task costs two container runs with a LaTeX compile inside, so
#            this is the real bottleneck and must NOT run at create's width.
#   report   Yield, bucketed by rejection reason, for human review.
#
# Publishing is deliberately not a stage here: it is an explicit, separate act.
#
# Credentials come from accountctl, which is the approved injection entry
# point. It cannot mount anything, so it produces the env file and this script
# starts the containers.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

usage() {
  cat <<'EOF'
Usage: scripts/run-batch.sh [options]

Options:
  --shards SPEC     Domain shard plan, e.g. "biology:3 physics:4 computer-science:2 mathematics:1"
                    (N shards for that domain). Default: one shard per known domain.
  --count N         Target tasks per shard (default 5).
  --dir DIR    Where per-shard run directories go (default /tmp/papersmith-batch).
  --account NAME    accountctl provider account (default: the provider name).
  --accept-jobs N   Concurrent Harbor acceptance workers (default 2).
  --stage STAGE     create | accept | report | all (default all).
  --resume          Continue existing run directories instead of recreating them.
  --no-build        Reuse the existing image instead of rebuilding it.
  -h, --help        Show this help.

Environment: LLM_PROVIDER, LLM_MODEL, LLM_REVIEW_MODEL are injected at run time
and are never defaulted in code.
EOF
}

shards_spec=""
count=5
run_root="/tmp/papersmith-batch"
account=""
accept_jobs=2
stage="all"
resume=false
no_build=false
SHARD_START_STAGGER_SECONDS="${SHARD_START_STAGGER_SECONDS:-8}"

while (($#)); do
  case "$1" in
    --shards) shards_spec="${2:?missing value for --shards}"; shift 2 ;;
    --count) count="${2:?missing value for --count}"; shift 2 ;;
    --dir) run_root="${2:?missing value for --dir}"; shift 2 ;;
    --account) account="${2:?missing value for --account}"; shift 2 ;;
    --accept-jobs) accept_jobs="${2:?missing value for --accept-jobs}"; shift 2 ;;
    --stage) stage="${2:?missing value for --stage}"; shift 2 ;;
    --resume) resume=true; shift ;;
    --no-build) no_build=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

# Only the create stage runs model sessions. Requiring a provider for accept or
# report made two read-only stages unusable without credentials.
provider="${LLM_PROVIDER:-}"
model="${LLM_MODEL:-}"
if [[ "$stage" == all || "$stage" == create ]]; then
  [[ -n "$provider" ]] || { echo "LLM_PROVIDER is required for the create stage (never defaulted)" >&2; exit 2; }
  [[ -n "$model" ]] || { echo "LLM_MODEL is required for the create stage (never defaulted)" >&2; exit 2; }
fi
review_model="${LLM_REVIEW_MODEL:-$model}"
account="${account:-$provider}"
image="${PAPERSMITH_IMAGE:-papersmith:e2e}"
ledger_dir="$run_root/ledger"
: "${shards_spec:=biology:1 physics:1 computer-science:1 mathematics:1}"

mkdir -p "$run_root" "$ledger_dir"

# Expand "domain:N" into concrete "domain i/N" shard assignments.
shard_plan=()
for entry in $shards_spec; do
  domain="${entry%%:*}"
  total="${entry##*:}"
  [[ "$total" =~ ^[0-9]+$ && "$total" -ge 1 ]] || { echo "invalid shard spec: $entry" >&2; exit 2; }
  for ((i = 1; i <= total; i++)); do
    shard_plan+=("$domain $i/$total")
  done
done
echo "batch plan: ${#shard_plan[@]} shard(s), target $count task(s) each, provider=$provider model=$model"

if [[ "$no_build" != true && ( "$stage" == all || "$stage" == create ) ]]; then
  echo "building $image"
  docker build --build-arg AGENT_NAME=papersmith -t "$image" -f docker/Dockerfile . >/tmp/papersmith-batch-build.log 2>&1 \
    || { echo "image build failed; see /tmp/papersmith-batch-build.log" >&2; exit 1; }
fi
# Fail fast on a stale image rather than discovering it once per shard: every
# worker would fail identically after the containers were already started.
if [[ "$stage" == all || "$stage" == create ]] && ! docker run --rm --entrypoint papersmith-cli "$image" create --help 2>&1 | grep -q -- '--shard'; then
  echo "image $image predates --shard/--ledger; rebuild it (drop --no-build)" >&2
  exit 2
fi

# --------------------------------------------------------------------------
# Credentials and the pi provider catalog. The catalog carries only a variable
# reference, never a key, so it is safe to write to a temp path.
# --------------------------------------------------------------------------
env_file="${PROVIDER_ENV_FILE:-}"
if [[ -z "$env_file" && ( "$stage" == all || "$stage" == create ) ]]; then
  env_file="/run/user/$(id -u)/papersmith-batch.$$.env"
  rm -f "$env_file"
  accountctl docker-run --providers "$account" --env-file-only --out "$env_file" >&2
  trap 'rm -f "$env_file"' EXIT
fi

models_file="${PI_MODELS_FILE:-}"
if [[ -z "$models_file" && ( "$stage" == all || "$stage" == create ) ]]; then
  models_file="$(mktemp /tmp/pi-models-container.XXXXXX.json)"
  python3 - "$HOME/.pi/agent/models.json" "$provider" "$models_file" <<'PY'
import json, re, sys
source, provider, dest = sys.argv[1], sys.argv[2], sys.argv[3]
providers = json.load(open(source)).get("providers") or {}
if provider not in providers:
    raise SystemExit(f"provider {provider!r} is not defined in {source}")
entry = dict(providers[provider])
entry["apiKey"] = "$" + re.sub(r"[^A-Za-z0-9]", "_", provider).upper() + "_API_KEY"
json.dump({"providers": {provider: entry}}, open(dest, "w"), indent=2)
PY
fi

run_dir_for() {  # domain, shard -> path
  printf '%s/%s-%s' "$run_root" "$1" "${2//\//of}"
}

# --------------------------------------------------------------------------
# Stage: create
# --------------------------------------------------------------------------
create_shard() {
  local domain="$1" shard="$2"
  local dir; dir="$(run_dir_for "$domain" "$shard")"
  local log="$dir.create.log"
  local mode=create
  if [[ -d "$dir" && -f "$dir/run.json" ]]; then
    if [[ "$resume" == true ]]; then
      mode=resume
    else
      echo "[$domain $shard] run directory exists; pass --resume to continue it" >&2
      return 2
    fi
  else
    rm -rf "$dir"; mkdir -p "$dir"
  fi

  local cmd=(papersmith create "discover and reconstruct $domain research papers"
    --selection discovery --domain "$domain" --shard "$shard" --count "$count"
    --output /tmp/run --ledger /tmp/ledger
    --provider "$provider" --model "$model" --review-model "$review_model")
  [[ "$mode" == resume ]] && cmd=(papersmith resume /tmp/run --shard "$shard" --ledger /tmp/ledger)

  echo "[$domain $shard] $mode -> $dir"
  docker run --rm \
    --env-file "$env_file" \
    --env AGENT_BACKEND=pi \
    --env "LLM_PROVIDER=$provider" --env "LLM_MODEL=$model" --env "LLM_REVIEW_MODEL=$review_model" \
    --env PI_CODING_AGENT_DIR=/root/.pi/agent \
    --env PAPERSMITH_LEDGER_DIR=/tmp/ledger \
    ${BOHR_ACCESS_KEY:+--env "BOHR_ACCESS_KEY=$BOHR_ACCESS_KEY"} \
    --mount "type=bind,src=$(realpath "$models_file"),dst=/root/.pi/agent/models.json,readonly" \
    -v "$dir:/tmp/run" -v "$ledger_dir:/tmp/ledger" \
    "$image" "${cmd[@]}" >"$log" 2>&1 \
    && echo "[$domain $shard] done" \
    || { echo "[$domain $shard] FAILED (see $log)" >&2; return 1; }
}

if [[ "$stage" == all || "$stage" == create ]]; then
  echo "=== create: ${#shard_plan[@]} shard(s) in parallel ==="
  pids=()
  stagger=0
  for assignment in "${shard_plan[@]}"; do
    read -r domain shard <<<"$assignment"
    # Stagger the starts: every shard opening its discovery query in the same
    # instant is what earns an HTTP 429 from arXiv.
    ( sleep "$stagger"; create_shard "$domain" "$shard" ) &
    pids+=($!)
    stagger=$((stagger + SHARD_START_STAGGER_SECONDS))
  done
  create_failures=0
  for pid in "${pids[@]}"; do wait "$pid" || create_failures=$((create_failures + 1)); done
  # A shard failing is normal at batch scale; the run continues with what it got.
  echo "create finished: $((${#pids[@]} - create_failures))/${#pids[@]} shard(s) succeeded"
  # The container writes as root; let the host read the evidence back.
  docker run --rm --entrypoint chmod -v "$run_root:/batch" "$image" -R a+rwX /batch >/dev/null 2>&1 || true
fi

# --------------------------------------------------------------------------
# Stage: accept. Bounded, because each task is two Harbor container runs.
# --------------------------------------------------------------------------
if [[ "$stage" == all || "$stage" == accept ]]; then
  echo "=== accept: real Harbor trials, $accept_jobs at a time ==="
  # Run directories are created by the control container as root; the host
  # worker must be able to write its receipt before any trial is paid for.
  docker run --rm --entrypoint chmod -v "$run_root:/batch" "$image" -R a+rwX /batch >/dev/null 2>&1 || true
  requests=()
  while IFS= read -r request; do
    receipt="${request/-request.json/-receipt.json}"
    # -s, not -f: a zero-byte receipt is not evidence of acceptance.
    [[ -s "$receipt" ]] && continue   # already accepted; never re-run a paid trial
    requests+=("$request")
  done < <(find "$run_root" -path '*/acceptance/*-request.json' -type f | sort)

  if ((${#requests[@]} == 0)); then
    echo "no pending acceptance requests"
  else
    printf '%s\0' "${requests[@]}" \
      | HARBOR_RUN_ENABLED=1 xargs -0 -P "$accept_jobs" -I{} \
          "$root/docker/run-acceptance-worker.sh" {} || true
  fi

  for run in "$run_root"/*/; do
    [[ -f "$run/run.json" ]] || continue
    docker run --rm -v "$run:/tmp/run" "$image" papersmith validate /tmp/run >"$run.validate.json" 2>&1 || true
  done
fi

# --------------------------------------------------------------------------
# Stage: report. What a human needs to judge the batch.
# --------------------------------------------------------------------------
if [[ "$stage" == all || "$stage" == report ]]; then
  echo "=== report ==="
  python3 "$root/scripts/batch-report.py" --dir "$run_root" --ledger "$ledger_dir"
fi
