"""PaperSmith deterministic run controller CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .acceptance import verify_acceptance_receipt
from .backends import doctor_report
from .config import ConfigError, RequestSpec
from .integrity import hash_json, sha256_file
from .pipeline import run_discovery, run_fixed
from .sources import BlockedError
from .state import RunLocked, RunState, STAGE_DIRS


def _build_spec(args) -> RequestSpec:
    spec = RequestSpec(
        request=args.request if getattr(args, "request", None) is not None else "",
        selection=args.selection if getattr(args, "selection", None) is not None else "discovery",
        papers=list(args.paper) if getattr(args, "paper", None) else [],
        count=args.count if getattr(args, "count", None) is not None else 1,
        output=args.output if getattr(args, "output", None) is not None else None,
        model=getattr(args, "model", None),
        review_model=getattr(args, "review_model", None),
        backend=getattr(args, "backend", None),
        source_roots=list(getattr(args, "source", None) or []),
        domain=getattr(args, "domain", None) or "biology",
    )
    spec.validate()
    return spec


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def cmd_doctor(args) -> int:
    _print_json(doctor_report())
    return 0


def cmd_create(args) -> int:
    spec = _build_spec(args)
    if args.describe:
        _print_json(spec.to_dict())
        return 0
    assert spec.output is not None
    if spec.output.exists() and any(spec.output.iterdir()):
        _print_json({"ok": False, "reason": f"output directory is non-empty: {spec.output}"})
        return 2
    state = RunState.create(spec.output, spec)
    state.acquire_lock()
    try:
        request_path = state.root / "inputs" / "request.json"
        request_path.write_text(json.dumps(spec.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        state.data["request_hash"] = sha256_file(request_path)
        state.append_event("request_snapshotted", request_hash=state.data["request_hash"])
        state.save()
    finally:
        state.release_lock()

    if spec.selection == "fixed":
        result = run_fixed(spec.output, spec, args)
    else:
        result = run_discovery(spec.output, spec, args)
    _print_json(result)
    return 0 if result.get("ok") else 2


def cmd_status(args) -> int:
    state = RunState.load(args.output)
    stages: dict[str, str] = {}
    for name in STAGE_DIRS:
        manifest = state.stage_dir(name) / "manifest.json"
        if manifest.is_file():
            stages[name] = json.loads(manifest.read_text(encoding="utf-8")).get("status", "unknown")
    _print_json({"run": state.data, "stages": stages})
    return 0


def cmd_resume(args) -> int:
    state = RunState.load(args.output)
    request_file = state.root / "inputs" / "request.json"
    if not request_file.is_file():
        _print_json({"ok": False, "reason": "request snapshot is missing"})
        return 2
    if sha256_file(request_file) != state.data.get("request_hash"):
        _print_json({"ok": False, "reason": "request inputs changed; downstream evidence invalidated"})
        return 2
    _print_json({"ok": True, "note": "resume re-runs run_fixed on the same workspace; not yet implemented incrementally"})
    return 0


def cmd_validate(args) -> int:
    state = RunState.load(args.output)
    failures: list[str] = []
    if not (state.root / "events.jsonl").is_file():
        failures.append("events.jsonl is missing")
    requests = sorted((state.root / "acceptance").glob("*-request.json"))
    if not requests:
        failures.append("no acceptance requests found")
    verified: dict[str, dict] = {}
    for request_path in requests:
        slug = request_path.name[: -len("-request.json")]
        receipt_path = request_path.with_name(f"{slug}-receipt.json")
        if not receipt_path.is_file():
            failures.append(f"acceptance receipt missing: {receipt_path.name}")
            continue
        request = json.loads(request_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        verification = verify_acceptance_receipt(receipt, request)
        if not verification.get("valid"):
            failures.append(f"acceptance receipt invalid for {slug}: {verification.get('issues')}")
            continue
        verified[slug] = {"receipt": receipt, "verification": verification}
    if failures:
        _print_json({"valid": False, "run": str(state.root), "failures": failures})
        return 1
    delivery = _assemble_delivery(state, verified)
    _print_json({"valid": True, "run": str(state.root), "delivery": delivery})
    return 0


def _assemble_delivery(state: RunState, verified: dict[str, dict]) -> dict:
    tasks: list[dict] = []
    for task_dir in sorted((state.root / "tasks").iterdir()):
        if not task_dir.is_dir():
            continue
        manifest = json.loads((task_dir / "manifest.json").read_text(encoding="utf-8")) if (task_dir / "manifest.json").is_file() else {}
        acceptance = None
        acc = verified.get(task_dir.name)
        if acc:
            acceptance = {
                "oracle_reward": acc["verification"]["oracle_reward"],
                "nop_reward": acc["verification"]["nop_reward"],
                "receipt_fingerprint": acc["verification"]["receipt_fingerprint"],
            }
        tasks.append(
            {"task_id": task_dir.name, "task_dir": str(task_dir), "manifest": manifest, "acceptance": acceptance}
        )
    gates: dict[str, str] = {}
    for gate in ("gate1", "gate2", "gate3"):
        m = state.stage_dir(gate) / "manifest.json"
        if m.is_file():
            gates[gate] = json.loads(m.read_text(encoding="utf-8")).get("status", "unknown")
    accepted = [t for t in tasks if t.get("acceptance")]
    delivery = {
        "agent": "papersmith",
        "request_hash": state.data.get("request_hash"),
        "tasks": tasks,
        "gates": gates,
        "acceptance": {
            "tasks_verified": len(accepted),
            "tasks_total": len(tasks),
            "all_oracle_one_nop_zero": all(
                t["acceptance"]["oracle_reward"] == 1 and t["acceptance"]["nop_reward"] == 0 for t in accepted
            ),
        },
    }
    delivery["delivery_hash"] = hash_json(delivery)
    (state.root / "delivery.json").write_text(
        json.dumps(delivery, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return delivery


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="papersmith")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("request")
    create.add_argument("--count", type=int, default=1)
    create.add_argument("--selection", choices=["fixed", "discovery"], default="discovery")
    create.add_argument("--paper", action="append")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--source", type=Path, action="append")
    create.add_argument("--backend", choices=["opencode"])
    create.add_argument("--provider")
    create.add_argument("--model")
    create.add_argument("--review-model")
    create.add_argument("--domain", choices=["biology", "physics"], default="biology")
    create.add_argument("--describe", action="store_true")
    create.set_defaults(fn=cmd_create)

    doctor = sub.add_parser("doctor")
    doctor.set_defaults(fn=cmd_doctor)

    status = sub.add_parser("status")
    status.add_argument("output", type=Path)
    status.set_defaults(fn=cmd_status)

    resume = sub.add_parser("resume")
    resume.add_argument("output", type=Path)
    resume.set_defaults(fn=cmd_resume)

    validate = sub.add_parser("validate")
    validate.add_argument("output", type=Path)
    validate.set_defaults(fn=cmd_validate)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (ConfigError, RunLocked, BlockedError) as exc:
        reason = getattr(exc, "reason", None) or str(exc)
        _print_json({"ok": False, "phase": getattr(exc, "phase", None), "reason": reason})
        return 2
    except RuntimeError as exc:
        _print_json({"ok": False, "reason": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
