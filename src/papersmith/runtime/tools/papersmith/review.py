"""Independent review contract and ReviewDecision execution.

Gate reviews run in a fresh backend session (separate from the producing
conversation) with only the frozen, hash-bound evidence for that gate. The
reviewer returns a structured ReviewDecision; the controller records the
session/response fingerprint and the input hash. A model judgment is evidence,
not an authoritative state change on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .backends import extract_json, run_phase
from .integrity import hash_json
from .sources import BlockedError

GATE1_CRITERIA = ["identity", "readability", "provenance", "license"]
GATE2_CRITERIA = ["accuracy", "sufficiency", "provenance", "license", "leakage"]
GATE3_CRITERIA = ["contract", "rubric", "separation", "oracle_provenance", "entrypoints"]


@dataclass
class ReviewDecision:
    gate: str
    decision: str  # pass | reject | blocked
    findings: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    recovery: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "gate": self.gate,
            "decision": self.decision,
            "findings": self.findings,
            "reasons": self.reasons,
            "recovery": self.recovery,
        }


def build_gate1_prompt(evidence: dict, input_hash: str) -> str:
    body = __import__("json").dumps(evidence, ensure_ascii=False, indent=2)
    return (
        "You are the independent Gate 1 scientific reviewer for a PaperSmith run. "
        "This is a fresh reviewer session, separate from the producing conversation. "
        "Review the frozen source evidence below against these criteria:\n"
        "  identity    - resolved metadata is consistent with the requested identifier (no silent substitution)\n"
        "  readability - the PDF is a real PDF (%%PDF signature, EOF marker, non-trivial size); a missing PDF for a paywalled DOI is a completeness finding, not fabrication\n"
        "  provenance  - retrieval hashes and source identity are recorded\n"
        "  license     - a license statement is present and compatible with the intended use; missing license means 'unverified', never 'pass'\n"
        f"Input hash: {input_hash}\n"
        "Evidence:\n"
        f"{body}\n\n"
        "Do not call any tools, read files, or run commands; the criteria above are complete "
        "and the evidence is already in this prompt. Answer with only the JSON object.\n"
        "Output a single JSON object with exactly these keys:\n"
        '  "gate": "gate1",\n'
        '  "decision": one of "pass", "reject", "blocked",\n'
        '  "findings": [{"criterion": <one of the four criteria>, "status": "pass"|"fail"|"unverified", "note": "..."}],\n'
        '  "reasons": ["..."],\n'
        '  "recovery": ["..."]\n'
        "Output only the JSON object."
    )


def _parse_decision(raw: dict | None) -> ReviewDecision | None:
    if not isinstance(raw, dict):
        return None
    decision = raw.get("decision")
    if decision not in ("pass", "reject", "blocked"):
        return None
    return ReviewDecision(
        gate="gate1",
        decision=decision,
        findings=[f for f in raw.get("findings", []) if isinstance(f, dict)],
        reasons=[str(r) for r in raw.get("reasons", [])],
        recovery=[str(r) for r in raw.get("recovery", [])],
    )


def run_gate1_review(
    backend: str,
    provider: str | None,
    model: str | None,
    evidence: dict,
    run_dir: str,
) -> dict:
    if not model:
        raise BlockedError("gate1", "no review model configured; set --review-model or --model")
    input_hash = hash_json(evidence)
    prompt = build_gate1_prompt(evidence, input_hash)
    result = run_phase(backend, provider, model, prompt, run_dir)
    stdout = result.get("stdout") or ""
    decision = _parse_decision(extract_json(stdout))
    return {
        "status": result.get("status"),
        "backend": result.get("backend"),
        "model": result.get("model"),
        "fingerprint": result.get("fingerprint"),
        "input_hash": input_hash,
        "decision": decision.to_dict() if decision else None,
        "reason": result.get("reason"),
        "stdout_tail": stdout[-2000:],
    }


def build_gate2_prompt(evidence: dict, input_hash: str) -> str:
    import json as _json

    body = _json.dumps(evidence, ensure_ascii=False, indent=2)
    return (
        "You are the independent Gate 2 scientific reviewer for a PaperSmith run. "
        "This is a fresh reviewer session, separate from the producing conversation. "
        "Review the frozen material evidence below against these criteria:\n"
        "  accuracy    - material records are scientifically consistent with the verified source (no invented facts, numbers, or causality)\n"
        "  sufficiency - all required material types are covered with substantive content (an explicit 'absent' note is honest, not sufficient)\n"
        "  provenance  - each record is bound to the source hash and a section/figure anchor\n"
        "  license     - the source license permits the intended reuse; missing license means 'unverified'\n"
        "  leakage     - public materials contain organized summaries, not verbatim source answer prose, private references, ground truth, or oracle content\n"
        f"Input hash: {input_hash}\n"
        "Evidence:\n"
        f"{body}\n\n"
        "Do not call any tools, read files, or run commands; the criteria above are complete "
        "and the evidence is already in this prompt. Answer with only the JSON object.\n"
        "Output a single JSON object with exactly these keys:\n"
        '  "gate": "gate2",\n'
        '  "decision": one of "pass", "reject", "blocked",\n'
        '  "findings": [{"criterion": <one of the five criteria>, "status": "pass"|"fail"|"unverified", "note": "..."}],\n'
        '  "reasons": ["..."],\n'
        '  "recovery": ["..."]\n'
        "Output only the JSON object."
    )


def run_gate2_review(
    backend: str,
    provider: str | None,
    model: str | None,
    evidence: dict,
    run_dir: str,
) -> dict:
    if not model:
        raise BlockedError("gate2", "no review model configured; set --review-model or --model")
    input_hash = hash_json(evidence)
    prompt = build_gate2_prompt(evidence, input_hash)
    result = run_phase(backend, provider, model, prompt, run_dir)
    stdout = result.get("stdout") or ""
    raw = extract_json(stdout)
    decision = None
    if isinstance(raw, dict) and raw.get("decision") in ("pass", "reject", "blocked"):
        decision = ReviewDecision(
            gate="gate2",
            decision=raw["decision"],
            findings=[f for f in raw.get("findings", []) if isinstance(f, dict)],
            reasons=[str(r) for r in raw.get("reasons", [])],
            recovery=[str(r) for r in raw.get("recovery", [])],
        )
    return {
        "status": result.get("status"),
        "backend": result.get("backend"),
        "model": result.get("model"),
        "fingerprint": result.get("fingerprint"),
        "input_hash": input_hash,
        "decision": decision.to_dict() if decision else None,
        "reason": result.get("reason"),
        "stdout_tail": stdout[-2000:],
    }


def build_gate3_prompt(evidence: dict, input_hash: str) -> str:
    import json as _json

    body = _json.dumps(evidence, ensure_ascii=False, indent=2)
    return (
        "You are the independent Gate 3 reviewer for a PaperSmith run. "
        "This is a fresh reviewer session, separate from the producing conversation. "
        "Review the frozen task below against these criteria:\n"
        "  contract         - instruction, task.toml and manifest agree on submission path, rubric and materials\n"
        "  rubric           - the rubric is explicit and scores the stated writing objective\n"
        "  separation       - public files contain no private/ground-truth/oracle references\n"
        "  oracle_provenance - the oracle is a newly written reference answer, not copied source prose\n"
        "  entrypoints      - required entrypoints are present (or explicitly pending for the pinned Harbor version)\n"
        f"Input hash: {input_hash}\n"
        "Evidence:\n"
        f"{body}\n\n"
        "Do not call any tools, read files, or run commands. Answer with only the JSON object.\n"
        "Output a single JSON object with exactly these keys:\n"
        '  "gate": "gate3",\n'
        '  "decision": one of "pass", "reject", "blocked",\n'
        '  "findings": [{"criterion": <one of the five criteria>, "status": "pass"|"fail"|"unverified", "note": "..."}],\n'
        '  "reasons": ["..."],\n'
        '  "recovery": ["..."]\n'
        "Output only the JSON object."
    )


def run_gate3_review(
    backend: str,
    provider: str | None,
    model: str | None,
    evidence: dict,
    run_dir: str,
) -> dict:
    if not model:
        raise BlockedError("gate3", "no review model configured; set --review-model or --model")
    input_hash = hash_json(evidence)
    prompt = build_gate3_prompt(evidence, input_hash)
    result = run_phase(backend, provider, model, prompt, run_dir)
    stdout = result.get("stdout") or ""
    raw = extract_json(stdout)
    decision = None
    if isinstance(raw, dict) and raw.get("decision") in ("pass", "reject", "blocked"):
        decision = ReviewDecision(
            gate="gate3",
            decision=raw["decision"],
            findings=[f for f in raw.get("findings", []) if isinstance(f, dict)],
            reasons=[str(r) for r in raw.get("reasons", [])],
            recovery=[str(r) for r in raw.get("recovery", [])],
        )
    return {
        "status": result.get("status"),
        "backend": result.get("backend"),
        "model": result.get("model"),
        "fingerprint": result.get("fingerprint"),
        "input_hash": input_hash,
        "decision": decision.to_dict() if decision else None,
        "reason": result.get("reason"),
        "stdout_tail": stdout[-2000:],
    }


def run_independent_review(gate: str, *args, **kwargs) -> ReviewDecision:
    raise BlockedError(
        gate,
        "independent review requires a specific gate runner (e.g. run_gate)",
    )


GATE_CRITERIA = {
    "gate1": "identity consistency, source availability, reducibility to a compilable template",
    "gate2": "overview faithfulness to the source, template compilability, references completeness, figure/table coverage (tables are optional when the source has none), public leakage",
    "gate3": "task tree contract, verifier correctness, public/private separation, oracle provenance, runnable entrypoints",
}


def run_gate(
    gate: str,
    evidence: dict,
    backend: str,
    provider: str | None,
    model: str | None,
    run_dir: str,
) -> dict:
    """Run one independent review gate and return a schema-valid verdict."""
    import json as _json

    if not model:
        raise BlockedError(gate, "no review model configured; set --review-model or --model")
    input_hash = hash_json(evidence)
    body = _json.dumps(evidence, ensure_ascii=False, indent=2)
    prompt = (
        f"You are the independent {gate} reviewer for a PaperSmith run. This is a fresh, "
        f"separate reviewer session. Criteria: {GATE_CRITERIA[gate]}. Do not call tools, read "
        f"files, or run commands; answer with only a JSON object.\n"
        f"Input hash: {input_hash}\nEvidence:\n{body}\n\n"
        'Output JSON with exactly: "gate": "' + gate + '", "decision": "pass"|"reject"|"blocked", '
        '"findings": [{"criterion": str, "status": "pass"|"fail"|"unverified", "note": str}], '
        '"reasons": [str], "recovery": [str]. Output only the JSON.'
    )
    result = run_phase(backend, provider, model, prompt, run_dir)
    stdout = result.get("stdout") or ""
    raw = extract_json(stdout)
    decision = None
    if isinstance(raw, dict) and raw.get("decision") in ("pass", "reject", "blocked"):
        decision = ReviewDecision(
            gate=gate,
            decision=raw["decision"],
            findings=[f for f in raw.get("findings", []) if isinstance(f, dict)],
            reasons=[str(r) for r in raw.get("reasons", [])],
            recovery=[str(r) for r in raw.get("recovery", [])],
        )
    return {
        "status": result.get("status"),
        "backend": result.get("backend"),
        "model": result.get("model"),
        "fingerprint": result.get("fingerprint"),
        "input_hash": input_hash,
        "decision": decision.to_dict() if decision else None,
        "reason": result.get("reason"),
        "stdout_tail": stdout[-2000:],
    }
