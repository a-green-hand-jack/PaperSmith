"""Trusted host acceptance contract and receipt verification.

Acceptance runs real Harbor oracle/nop trials through a trusted host worker.
This module defines the hash-bound request and the deterministic receipt
verifier: a receipt is valid only when it matches the request hashes, carries
trial IDs and exit statuses, and shows oracle reward == 1 and nop reward == 0.
It never fabricates a receipt and never grants Docker/Harbor control to the
producing or writing agent.
"""
from __future__ import annotations

import json
from pathlib import Path

from .integrity import hash_json


def build_acceptance_request(task_id: str, task_dir: Path, manifest: dict, oracle: dict) -> dict:
    request = {
        "task_id": task_id,
        "task_dir": str(task_dir),
        "manifest": manifest,
        "oracle": oracle,
        "oracle_trial": {"expect_reward": 1},
        "nop_trial": {"expect_reward": 0},
    }
    request["request_hash"] = hash_json(request)
    return request


def verify_acceptance_receipt(receipt: dict, request: dict) -> dict:
    issues: list[str] = []
    if not isinstance(receipt, dict):
        return {"valid": False, "issues": ["receipt is not an object"]}
    if receipt.get("request_hash") != request.get("request_hash"):
        issues.append("receipt request_hash does not match the acceptance request")
    if receipt.get("task_id") != request.get("task_id"):
        issues.append("receipt task_id does not match the acceptance request")
    trials = receipt.get("trials") or {}
    oracle = trials.get("oracle") or {}
    nop = trials.get("nop") or {}
    for name, trial in (("oracle", oracle), ("nop", nop)):
        if not trial.get("trial_id"):
            issues.append(f"missing {name} trial_id")
        if not isinstance(trial.get("reward"), (int, float)):
            issues.append(f"missing numeric {name} reward")
        if not isinstance(trial.get("exit_status"), int):
            issues.append(f"missing {name} exit_status")
    if oracle.get("reward") != 1:
        issues.append(f"oracle reward must be 1, got {oracle.get('reward')!r}")
    if nop.get("reward") != 0:
        issues.append(f"nop reward must be 0, got {nop.get('reward')!r}")
    if not isinstance(receipt.get("artifact_hashes"), dict):
        issues.append("receipt is missing artifact_hashes")
    return {
        "valid": not issues,
        "issues": issues,
        "oracle_reward": oracle.get("reward"),
        "nop_reward": nop.get("reward"),
        "receipt_fingerprint": hash_json(receipt),
    }


def write_acceptance_request(path: Path, request: dict) -> dict:
    data = json.dumps(request, indent=2, ensure_ascii=False).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data + b"\n")
    return {"path": str(path), "sha256": hash_json(request), "bytes": len(data)}
