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

import datetime
import json
import os
from pathlib import Path

USED_FILE = "used-papers.jsonl"
REJECTED_FILE = "rejected-papers.jsonl"
# A candidate the pipeline never got to judge: the fetch failed in a way that
# says "later", not "no". These are recorded so the loss is visible, and are
# deliberately NOT part of the exclusion set — a transient 429, a read timeout,
# or a source endpoint serving 404 while it throttles us must not cost a good
# paper its place in the batch. One sweep of arXiv soft-404s burned 53 of them.
DEFERRED_FILE = "deferred-papers.jsonl"
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
    # Without a time on each row a cluster of failures cannot be told from a
    # steady trickle, which is the difference between "these papers are bad" and
    # "the upstream was degraded for twenty minutes".
    record.setdefault("recorded_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
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
    """Every paper this batch already used or judged unusable.

    Deferred papers are excluded from this set on purpose: they were never
    judged, so skipping them forever would turn one bad minute upstream into a
    permanent loss.
    """
    if directory is None:
        return set()
    return _read_papers(directory / USED_FILE) | _read_papers(directory / REJECTED_FILE)


def record_used(directory: Path | None, paper: str, task_dir: str, domain: str) -> None:
    if directory is None:
        return
    _append(directory / USED_FILE, {"paper": paper, "task_dir": task_dir, "domain": domain})


def record_rejected(directory: Path | None, paper: str, reason: str, domain: str) -> None:
    """Record a paper this batch judged unusable. Permanent for this batch."""
    if directory is None:
        return
    _append(directory / REJECTED_FILE, {"paper": paper, "reason": reason, "domain": domain})


def record_deferred(directory: Path | None, paper: str, reason: str, domain: str) -> None:
    """Record a candidate lost to a transient failure, still eligible later."""
    if directory is None:
        return
    _append(directory / DEFERRED_FILE, {"paper": paper, "reason": reason, "domain": domain})


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
    deferred = directory / DEFERRED_FILE
    used_total = _count_papers(used)
    rejected_total = _count_papers(rejected)
    deferred_total = _count_papers(deferred)
    judged = used_total + rejected_total
    return {
        "ledger": str(directory),
        "used": used_total,
        "rejected": rejected_total,
        "deferred": deferred_total,
        # Two denominators, because they answer two different questions and
        # quoting either one alone misleads. "judged" excludes candidates the
        # pipeline never got to evaluate, so it is the number that moves when the
        # pipeline itself changes. "attempted" includes them, so it is the number
        # that says what the batch actually cost.
        "judged": judged,
        "attempted": judged + deferred_total,
        "yield_of_judged": round(used_total / judged, 4) if judged else None,
        "yield_of_attempted": (
            round(used_total / (judged + deferred_total), 4) if judged + deferred_total else None
        ),
        "rejection_reasons": _bucket_reasons(rejected),
        "deferred_reasons": _bucket_reasons(deferred),
    }


def _bucket_reasons(path: Path) -> dict[str, int]:
    """Count records by failure mode: the reason's clause before the first colon."""
    buckets: dict[str, int] = {}
    if not path.is_file():
        return buckets
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        mode = str(record.get("reason") or "unknown").split(":", 1)[0].strip()[:80]
        buckets[mode] = buckets.get(mode, 0) + 1
    return dict(sorted(buckets.items(), key=lambda kv: -kv[1]))
