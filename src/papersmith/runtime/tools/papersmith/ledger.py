"""Cross-run paper ledger for parallel batches.

Ten workers sharding one corpus still collide: a paper cross-listed in two
domains is a legitimate candidate for both, and a rerun after a crash would
otherwise pay for the same rejection twice. The ledger is a host-side,
append-only record shared by every worker in a batch.

Appends are single `write` calls of one line each on a file opened `O_APPEND`.
On POSIX that is atomic below PIPE_BUF, which is what makes concurrent writers
safe without a lock; a line longer than that is truncated rather than allowed
to interleave. Readers tolerate a partial trailing line.

The ledger is an optimisation and a record, never an authority: a paper absent
from it is simply unseen, and the per-run event log remains the evidence chain.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

USED_FILE = "used-papers.jsonl"
REJECTED_FILE = "rejected-papers.jsonl"
LEDGER_ENV = "PAPERSMITH_LEDGER_DIR"
# Keep a record comfortably inside PIPE_BUF (4096 on Linux) so the append stays
# atomic; reasons are the only unbounded field.
MAX_RECORD_BYTES = 2048


def ledger_dir(explicit: str | Path | None = None) -> Path | None:
    """Resolve the shared ledger directory, or None when a batch has none."""
    value = explicit if explicit is not None else os.environ.get(LEDGER_ENV)
    if not value:
        return None
    return Path(value).expanduser()


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    data = line.encode("utf-8")
    if len(data) + 1 > MAX_RECORD_BYTES:
        record = dict(record)
        record["reason"] = str(record.get("reason", ""))[:200] + "…(truncated)"
        data = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, data + b"\n")
    finally:
        os.close(fd)


def _canonical(paper: str) -> str:
    return paper.removeprefix("arXiv:")


def _read_papers(path: Path) -> set[str]:
    """Every recorded identifier plus its bare form, for exclusion matching.

    Both spellings are returned deliberately: a candidate may arrive as either
    `arXiv:2601.02265` or `2601.02265`, and both must match. Use
    `_count_papers` when the question is "how many papers", not "is this one
    already seen".
    """
    if not path.is_file():
        return set()
    papers: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn trailing line from a killed writer
        paper = record.get("paper")
        if isinstance(paper, str) and paper:
            papers.add(paper)
            papers.add(_canonical(paper))
    return papers


def _count_papers(path: Path) -> int:
    """Distinct papers recorded, counting each identifier once."""
    if not path.is_file():
        return 0
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        paper = record.get("paper")
        if isinstance(paper, str) and paper:
            seen.add(_canonical(paper))
    return len(seen)


def load_excluded(directory: Path | None) -> set[str]:
    """Every paper any worker in this batch already used or rejected."""
    if directory is None:
        return set()
    return _read_papers(directory / USED_FILE) | _read_papers(directory / REJECTED_FILE)


def record_used(directory: Path | None, paper: str, task_dir: str, domain: str) -> None:
    if directory is None:
        return
    _append(directory / USED_FILE, {"paper": paper, "task_dir": task_dir, "domain": domain})


def record_rejected(directory: Path | None, paper: str, reason: str, domain: str) -> None:
    if directory is None:
        return
    _append(directory / REJECTED_FILE, {"paper": paper, "reason": reason, "domain": domain})


def yield_report(directory: Path | None) -> dict:
    """Batch yield, bucketed by rejection reason.

    This is the number that says whether a change to the pipeline helped: how
    many candidates were considered, how many became tasks, and where the rest
    were lost.
    """
    if directory is None:
        return {"ledger": None}
    used = directory / USED_FILE
    rejected = directory / REJECTED_FILE
    buckets: dict[str, int] = {}
    if rejected.is_file():
        for line in rejected.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            reason = str(record.get("reason") or "unknown")
            # Bucket on the reason's leading clause: the detail after the colon
            # is per-paper, the clause before it is the failure mode.
            buckets[reason.split(":", 1)[0].strip()[:80]] = (
                buckets.get(reason.split(":", 1)[0].strip()[:80], 0) + 1
            )
    used_total = _count_papers(used)
    rejected_total = _count_papers(rejected)
    considered = used_total + rejected_total
    return {
        "ledger": str(directory),
        "considered": considered,
        "used": used_total,
        "rejected": rejected_total,
        "yield": round(used_total / considered, 4) if considered else None,
        "rejection_reasons": dict(sorted(buckets.items(), key=lambda kv: -kv[1])),
    }
