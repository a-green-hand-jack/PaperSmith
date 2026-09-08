"""Deterministic hashing and manifest helpers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def hash_json(value: object) -> str:
    return sha256_bytes(canonical_json(value))


def file_manifest(paths: list[Path], base: Path) -> dict[str, str]:
    """Relative-path -> SHA-256 manifest for an explicit file allowlist."""
    manifest: dict[str, str] = {}
    for path in sorted(paths):
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(base.resolve())
        except ValueError:
            raise ValueError(f"path outside run root: {path}")
        if not resolved.is_file():
            raise ValueError(f"manifest entry is not a file: {path}")
        manifest[relative.as_posix()] = sha256_file(resolved)
    return manifest
