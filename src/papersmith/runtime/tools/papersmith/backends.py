"""Backend and environment discovery plus the phase-scoped session adapter.

The adapter runs one role-scoped, non-interactive pi session per phase with a
controller-supplied phase prompt, and returns the raw output plus a SHA-256
response fingerprint. It never fabricates a session or response.

Provider and model are never chosen here. They arrive from the request spec
(CLI flags or environment) and are passed through verbatim, so swapping the
LLM never requires a code change. A missing provider or model is an error, not
a silent fallback to whatever pi would default to.

The session is hardened by pi flags rather than by prompt text: `--no-tools`
enforces the read-only role, and `--print --no-session` guarantees a phase
leaves no session behind. pi has no `--timeout`, so the caller's subprocess
timeout is the only turn bound available.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys

BACKENDS = ("pi",)
DEFAULT_BACKEND = BACKENDS[0]

# Ambient discovery must stay closed: a phase session may only see the prompt it
# was given, never the host's skills, extensions, prompt templates or AGENTS.md.
PI_ISOLATION_FLAGS = (
    "--no-context-files",
    "--no-approve",
    "--no-skills",
    "--no-extensions",
    "--no-prompt-templates",
)


class BackendUnavailable(RuntimeError):
    pass


def discover_backends() -> dict[str, bool]:
    return {name: shutil.which(name) is not None for name in BACKENDS}


def discover_document_tools() -> dict[str, bool]:
    """Best-effort presence checks; presence is not capability evidence."""
    return {
        "pdf_text": any(shutil.which(t) for t in ("pdftotext", "mutool", "qpdf")),
        "tex": any(shutil.which(t) for t in ("pdflatex", "tectonic", "latexmk")),
        "docker": shutil.which("docker") is not None,
    }


def capability_flags() -> dict[str, str]:
    return {
        "request_planning": "implemented",
        "source_acquisition": "implemented",
        "material_curation": "implemented",
        "scientific_review": "implemented",
        "task_conversion": "implemented",
        "acceptance": "implemented",
        "recovery": "implemented",
        "validation": "partial",
    }


def doctor_report() -> dict:
    return {
        "status": "implemented",
        "python": sys.version.split()[0],
        "backends": discover_backends(),
        "document_tools": discover_document_tools(),
        "model_discovery": "not-determinable-without-provider-credentials",
        "capabilities": capability_flags(),
    }


def find_backend() -> str | None:
    """Locate the pi executable that runs phase sessions."""
    return shutil.which("pi")


def run_phase(
    backend: str,
    provider: str | None,
    model: str | None,
    prompt: str,
    cwd: str,
    timeout: int = 300,
) -> dict:
    """Run one non-interactive, tool-less pi session and return typed evidence."""
    if backend not in BACKENDS:
        raise BackendUnavailable(f"unsupported backend: {backend} (this Agent supports pi only)")
    pi_bin = find_backend()
    if not pi_bin:
        raise BackendUnavailable("pi executable not found on PATH")
    if not provider:
        raise BackendUnavailable("a provider is required; it is injected at runtime, never defaulted")
    if not model:
        raise BackendUnavailable("a model is required; it is injected at runtime, never defaulted")

    args = [
        pi_bin,
        "--provider",
        provider,
        "--model",
        model,
        *PI_ISOLATION_FLAGS,
        "--no-tools",
        "--print",
        "--no-session",
        "--",
        prompt,
    ]
    env = dict(os.environ)
    env.pop("AGENT_OUTPUT_FORMAT", None)  # plain text so the phase prompt can be parsed
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            errors="replace",
            cwd=cwd,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "blocked",
            "backend": backend,
            "provider": provider,
            "model": model,
            "reason": f"phase session timed out after {timeout}s",
            "fingerprint": "",
        }
    stdout = proc.stdout or ""
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "backend": backend,
        "provider": provider,
        "model": model,
        "stdout": stdout,
        "stderr": (proc.stderr or "")[-2000:],
        "returncode": proc.returncode,
        "fingerprint": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
    }


def extract_json(text: str) -> dict | None:
    """Extract the first balanced JSON object from model text, if any."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
