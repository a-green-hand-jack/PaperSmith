#!/usr/bin/env python3
"""Build and inspect the PaperSmith product infrastructure without secrets."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run(label: str, command: list[str]) -> bool:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        print(f"ERROR {label}: {detail[-1] if detail else 'command failed'}")
        return False
    print(f"PASS  {label}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--image")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    image = args.image or f"{args.agent}:infra"
    required = [
        "distribution/install.sh", "distribution/launcher", "distribution/container-entrypoint.sh",
        "docker/Dockerfile", "docker/run-papersmith-e2e.sh", "scripts/validate-definition.sh",
    ]
    ok = True
    for relative in required:
        if not (root / relative).is_file():
            print(f"ERROR required-file: missing {relative}")
            ok = False
    ok = run("definition", ["./scripts/validate-definition.sh", args.agent]) and ok
    for directory in ("distribution", "docker", "scripts"):
        for path in (root / directory).rglob("*.sh"):
            ok = run(f"syntax {path.relative_to(root)}", ["bash", "-n", str(path)]) and ok
    if not shutil.which("docker"):
        print("ERROR docker: Docker is unavailable")
        return 1
    if not args.skip_build:
        ok = run("docker-build", ["docker", "build", "--build-arg", f"AGENT_NAME={args.agent}", "-t", image, "-f", "docker/Dockerfile", "."]) and ok
    smoke = "; ".join([
        "set -eu", "command -v opencode", "command -v codex", "command -v claude",
        f"{args.agent} --help >/dev/null", f"{args.agent} --version >/dev/null",
        "test -z \"$(find /opt/install -name AGENTS.md -print -quit)\"",
        f"test ! -d /opt/install/lib/{args.agent}/agent-definition/.agents",
        f"test ! -d /opt/install/lib/{args.agent}/agent-definition/development",
    ])
    ok = run("docker-runtime", ["docker", "run", "--rm", "--entrypoint", "bash", image, "-c", smoke]) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
