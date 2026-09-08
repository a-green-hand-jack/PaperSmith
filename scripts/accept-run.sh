#!/usr/bin/env bash
# Run REAL Harbor acceptance for every pending acceptance request in a run dir,
# then validate the run (assembles delivery.json) inside the papersmith image.
#
# The acceptance worker runs on the HOST (it needs the `harbor` CLI + Docker);
# `papersmith validate` runs inside the image (it needs the papersmith package).
# This script is the single entrypoint for the acceptance + delivery stage.
set -euo pipefail

run_dir="${1:?usage: $0 <run-dir> [image]}"
image="${2:-papersmith:e2e}"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
worker="$root/docker/run-acceptance-worker.sh"

accept_dir="$run_dir/acceptance"
test -d "$accept_dir" || { echo "no acceptance dir: $accept_dir" >&2; exit 2; }

shopt -s nullglob
requests=("$accept_dir"/*-request.json)
shopt -u nullglob
if [[ ${#requests[@]} -eq 0 ]]; then
  echo "no acceptance requests found in $accept_dir" >&2
  exit 2
fi

echo "=== acceptance: ${#requests[@]} task(s) ==="
for request in "${requests[@]}"; do
  slug="$(basename "$request" | sed 's/-request\.json$//')"
  echo "--- accepting $slug ---"
  HARBOR_JOBS_DIR="${HARBOR_JOBS_DIR:-/tmp/papersmith-acceptance-jobs}" "$worker" "$request"
done

echo "=== validate (assembles delivery.json) ==="
docker run --rm --entrypoint chmod -v "$run_dir:/tmp/run" "$image" -R a+rwX /tmp/run >/dev/null
docker run --rm -v "$run_dir:/tmp/run" "$image" papersmith validate /tmp/run
