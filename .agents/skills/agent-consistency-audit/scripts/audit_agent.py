#!/usr/bin/env python3
"""Audit a PaperSmith Agent definition and optional release archive."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path


SECRET_NAME = re.compile(r"(?:^\.env(?:\..*)?$|auth\.json$|credential|secret|token|private[-_]?key)", re.I)


def finding(level: str, message: str) -> None:
    print(f"{level}: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--release", type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    runtime = root / "src" / args.agent / "runtime"
    failures = 0

    manifest = root / "src" / args.agent / "agent.yaml"
    required = [manifest, runtime / "identity.md", runtime / "memory-policy.md", runtime / "package.json"]
    required.extend(runtime / name for name in ("knowledge", "skills", "workflows"))
    for path in required:
        if not path.exists():
            finding("ERROR", f"missing required path: {path.relative_to(root)}")
            failures += 1
    if failures:
        return 1

    manifest_text = manifest.read_text(encoding="utf-8")
    if not re.search(rf"^name:\s*{re.escape(args.agent)}\s*$", manifest_text, re.M):
        finding("ERROR", "agent.yaml name does not match --agent")
        failures += 1
    try:
        config = json.loads((runtime / "package.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        finding("ERROR", f"invalid runtime/package.json: {exc}")
        failures += 1
    else:
        # Shallow manifest consistency only; validate-definition.sh owns the
        # full pi manifest contract.
        section = config.get("agent")
        if not isinstance(section, dict) or section.get("backend") != "pi":
            finding("ERROR", "runtime/package.json agent.backend must be pi")
            failures += 1
        if "./skills" not in (config.get("pi", {}) or {}).get("skills", []):
            finding("ERROR", "runtime/package.json pi.skills must include ./skills")
            failures += 1
    if not list((runtime / "skills").rglob("SKILL.md")):
        finding("ERROR", "runtime has no product SKILL.md")
        failures += 1
    for path in runtime.rglob("*"):
        if path.is_file() and SECRET_NAME.search(path.name):
            finding("ERROR", f"credential-like runtime path: {path.relative_to(root)}")
            failures += 1
    for path in root.glob("**/*.sh"):
        if any(part in {".git", "release", "node_modules", ".venv"} for part in path.parts):
            continue
        if subprocess.run(["bash", "-n", str(path)], check=False).returncode:
            finding("ERROR", f"shell syntax: {path.relative_to(root)}")
            failures += 1
    if args.release:
        try:
            with tarfile.open(args.release, "r:gz") as archive:
                names = archive.getnames()
        except (OSError, tarfile.TarError) as exc:
            finding("ERROR", f"cannot read release archive: {exc}")
            failures += 1
        else:
            for name in names:
                parts = Path(name).parts
                if "AGENTS.md" in parts or ".agents" in parts or "development" in parts or (parts and SECRET_NAME.search(parts[-1])):
                    finding("ERROR", f"development or credential path in release: {name}")
                    failures += 1
    if failures:
        finding("SUMMARY", f"{failures} error(s)")
        return 1
    finding("PASS", f"{args.agent} definition and product boundary are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
