"""Backend and environment discovery plus the phase-scoped session adapter.

The adapter reuses the installed product launcher for backend wiring (auth,
CLI flags, sandbox). It invokes one role-scoped, non-interactive session per
phase with a controller-supplied phase prompt, and returns the raw output plus
a SHA-256 response fingerprint. It never fabricates a session or response.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys

BACKENDS = ("opencode", "codex", "claude", "pi")


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
        "recovery": "partial",
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


def find_launcher() -> str | None:
    """Locate the installed product launcher, not this control CLI."""
    return shutil.which("papersmith")


def run_phase(
    backend: str,
    provider: str | None,
    model: str | None,
    prompt: str,
    cwd: str,
    timeout: int = 300,
) -> dict:
    """Run one non-interactive backend session and return typed evidence."""
    launcher = find_launcher()
    if not launcher:
        raise BackendUnavailable("installed papersmith launcher not found on PATH")
    args = [launcher, "--backend", backend]
    if provider:
        args += ["--provider", provider]
    if model:
        args += ["--model", model]
    args += [prompt]
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
            "model": model,
            "reason": f"phase session timed out after {timeout}s",
            "fingerprint": "",
        }
    stdout = proc.stdout or ""
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "backend": backend,
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
