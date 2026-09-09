#!/usr/bin/env python3
"""Batch review surface for a human reviewer.

Quality in this pipeline is judged by a person looking at the tasks, not by an
automated scorer. This script therefore reports facts a reviewer needs and
stops there: it computes no quality score and makes no accept/reject
recommendation.

Two questions it answers:
  1. Per task: what was built, did the deterministic checks hold, and what did
     the real Harbor trials actually return.
  2. Per batch: the yield, bucketed by why candidates were lost — the number
     that says where the pipeline is leaking.

Read-only. Requires no credentials.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src/papersmith/runtime/tools"))
try:
    from papersmith.ledger import yield_report
except ImportError:  # the tools package is optional for a report-only checkout
    yield_report = None  # type: ignore[assignment]


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _materials_shape(task_dir: Path) -> dict:
    materials = task_dir / "environment" / "materials"
    overview = materials / "research_overview.md"
    text = overview.read_text(encoding="utf-8", errors="replace") if overview.is_file() else ""
    inventory = _read_json(materials / "table_inventory.json") or {}
    tables = inventory.get("tables") if isinstance(inventory, dict) else None
    return {
        "overview_words": len(text.split()),
        "figures": len(list((materials / "figures").glob("*"))) if (materials / "figures").is_dir() else 0,
        "tables": len(tables) if isinstance(tables, list) else (
            len(list((materials / "tables").glob("*.tex"))) if (materials / "tables").is_dir() else 0
        ),
        "references": len(re.findall(r"^@\w+\{", (materials / "references.bib").read_text(
            encoding="utf-8", errors="replace") if (materials / "references.bib").is_file() else "", re.M)),
    }


def _acceptance(run_dir: Path, slug: str) -> dict:
    receipt = _read_json(run_dir / "acceptance" / f"{slug}-receipt.json")
    if not receipt:
        return {"state": "pending"}
    trials = receipt.get("trials") or {}
    oracle = (trials.get("oracle") or {}).get("reward")
    nop = (trials.get("nop") or {}).get("reward")
    accepted = oracle == 1 and nop == 0
    return {
        "state": "accepted" if accepted else "failed",
        "oracle": oracle,
        "nop": nop,
        "oracle_exit": (trials.get("oracle") or {}).get("exit_status"),
        "nop_exit": (trials.get("nop") or {}).get("exit_status"),
    }


def collect(run_root: Path) -> list[dict]:
    rows: list[dict] = []
    for run_dir in sorted(p for p in run_root.iterdir() if (p / "run.json").is_file()):
        run = _read_json(run_dir / "run.json") or {}
        domain = (run.get("request") or {}).get("domain", "?")
        gates: dict[str, str] = {}
        for name in ("gate1", "gate2", "gate3"):
            manifest = _read_json(run_dir / "stages" / name / "manifest.json") or {}
            gates[name] = manifest.get("status", "-")
        tasks_dir = run_dir / "tasks"
        if not tasks_dir.is_dir():
            continue
        for task_dir in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
            manifest = _read_json(task_dir / "manifest.json") or {}
            rows.append(
                {
                    "run": run_dir.name,
                    "domain": domain,
                    "paper": manifest.get("paper") or task_dir.name,
                    "title": (manifest.get("title") or "")[:70],
                    "task_dir": str(task_dir),
                    "gates": gates,
                    "materials": _materials_shape(task_dir),
                    "acceptance": _acceptance(run_dir, task_dir.name),
                    "ground_truth_pdf": (task_dir / "solution" / "private" / "main.pdf").is_file(),
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", dest="runs", type=Path, required=True, help="directory holding per-shard run directories")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--json", action="store_true", help="emit the rows as JSON")
    args = parser.parse_args()

    if not args.runs.is_dir():
        print(f"run root does not exist: {args.runs}", file=sys.stderr)
        return 2
    rows = collect(args.runs)
    report = yield_report(args.ledger) if (yield_report and args.ledger) else {"ledger": None}

    if args.json:
        print(json.dumps({"tasks": rows, "yield": report}, indent=2, ensure_ascii=False))
        return 0

    if not rows:
        print("no tasks found under", args.runs)
    else:
        print(f"{'paper':<22} {'domain':<17} {'gates':<14} {'ovw':>5} {'fig':>4} {'tab':>4} {'ref':>4}  acceptance")
        print("-" * 104)
        for row in rows:
            gates = "/".join(row["gates"][g][:4] for g in ("gate1", "gate2", "gate3"))
            mat = row["materials"]
            acc = row["acceptance"]
            verdict = (
                f"oracle={acc['oracle']} nop={acc['nop']}" if acc["state"] != "pending" else "pending"
            )
            print(
                f"{row['paper']:<22} {row['domain']:<17} {gates:<14} "
                f"{mat['overview_words']:>5} {mat['figures']:>4} {mat['tables']:>4} {mat['references']:>4}"
                f"  {acc['state']}: {verdict}"
            )
        accepted = sum(1 for r in rows if r["acceptance"]["state"] == "accepted")
        print(f"\n{accepted}/{len(rows)} task(s) accepted (oracle=1 and nop=0)")

    if report.get("ledger"):
        print(
            f"\nbatch yield (of judged): {report['used']}/{report['judged']}"
            f" ({report['yield_of_judged']})"
        )
        for reason, hits in report["rejection_reasons"].items():
            print(f"  {hits:>4}  {reason}")
        if report.get("deferred"):
            # Reported separately and never folded into the judged yield: these
            # candidates were lost upstream, so counting them as pipeline
            # rejections would blame the pipeline for someone else's bad minute.
            print(
                f"\n  plus {report['deferred']} candidate(s) deferred, never judged"
                f" -> yield of all {report['attempted']} attempted:"
                f" {report['yield_of_attempted']}"
            )
            for reason, hits in report["deferred_reasons"].items():
                print(f"  {hits:>4}  {reason}")
    print("\nGate verdicts are recorded evidence, not a quality score. The only")
    print("acceptance signal is a real Harbor receipt with oracle=1 and nop=0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
