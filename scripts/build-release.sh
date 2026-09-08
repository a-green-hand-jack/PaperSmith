#!/usr/bin/env bash
set -euo pipefail
name="${1:?usage: $0 <agent-name> [version]}"
version="${2:-0.1.0}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$root/release/$name-$version"
[[ ! -e "$out" ]] || { echo "release output already exists: $out" >&2; exit 2; }
mkdir -p "$out/agent-definition" "$out/bin"
tar -C "$root/src/$name/runtime" --exclude=AGENTS.md --exclude=node_modules \
  --exclude=__pycache__ --exclude='*.egg-info' --exclude=build \
  -cf - . | tar -C "$out/agent-definition" -xf -
[[ -f "$out/agent-definition/package.json" ]] || {
  echo "release payload is missing package.json (the pi resource manifest)" >&2
  exit 2
}
cp "$root/distribution/launcher" "$out/launcher"
cp "$root/distribution/install.sh" "$out/install.sh"
cp "$root/distribution/launcher" "$out/bin/$name"
release_url="${RELEASE_URL:-__RELEASE_URL__}"
release_backends="${AGENT_BACKENDS:-pi}"
[[ "$release_backends" =~ ^(pi|pi-coding-agent)$ ]] || {
  echo "invalid AGENT_BACKENDS: $release_backends (this Agent supports pi only)" >&2
  exit 2
}
sed -i '' "s/AGENT_NAME=\"\${AGENT_NAME:-papersmith}\"/AGENT_NAME=\"\${AGENT_NAME:-$name}\"/; s/AGENT_BACKENDS=\"\${AGENT_BACKENDS:-pi}\"/AGENT_BACKENDS=\"\${AGENT_BACKENDS:-$release_backends}\"/; s/__AGENT_NAME__/$name/g; s#__RELEASE_URL__#$release_url#g" "$out/install.sh" 2>/dev/null \
  || sed -i "s/AGENT_NAME=\"\${AGENT_NAME:-papersmith}\"/AGENT_NAME=\"\${AGENT_NAME:-$name}\"/; s/AGENT_BACKENDS=\"\${AGENT_BACKENDS:-pi}\"/AGENT_BACKENDS=\"\${AGENT_BACKENDS:-$release_backends}\"/; s/__AGENT_NAME__/$name/g; s#__RELEASE_URL__#$release_url#g" "$out/install.sh"
sed -i '' "s/__AGENT_NAME__/$name/g" "$out/launcher" "$out/bin/$name" 2>/dev/null \
  || sed -i "s/__AGENT_NAME__/$name/g" "$out/launcher" "$out/bin/$name"
chmod +x "$out/bin/$name"
chmod +x "$out/install.sh" "$out/launcher"
printf '{"agent":"%s","version":"%s","definition":"src/%s/runtime","provider":"runtime-injected","backend":"pi","pi":"%s","development_resources":"excluded"}\n' \
  "$name" "$version" "$name" "${PI_VERSION:-latest}" > "$out/release-manifest.json"
tar -C "$root/release" -czf "$root/release/$name-$version.tar.gz" "$name-$version"
echo "built release/$name-$version.tar.gz"
