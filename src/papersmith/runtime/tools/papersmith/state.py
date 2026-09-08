"""Run workspace state: layout, lock, run.json and append-only events."""
from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import RequestSpec
from .integrity import hash_json

STAGE_DIRS = ["proposal", "gate1", "materials", "gate2", "conversion", "gate3"]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunLocked(RuntimeError):
    pass


class RunState:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.data: dict = {}
        self._lock_fd: int | None = None

    # -- creation / loading -------------------------------------------------
    @classmethod
    def create(cls, root: Path, spec: RequestSpec) -> "RunState":
        root = root.resolve()
        if root.exists() and any(root.iterdir()):
            raise RuntimeError(f"output directory is non-empty: {root}")
        root.mkdir(parents=True, exist_ok=True)
        for name in STAGE_DIRS:
            (root / "stages" / name).mkdir(parents=True, exist_ok=True)
        (root / "inputs").mkdir(parents=True, exist_ok=True)
        (root / "acceptance").mkdir(parents=True, exist_ok=True)
        (root / "tasks").mkdir(parents=True, exist_ok=True)
        state = cls(root)
        state.data = {
            "version": 1,
            "agent": "papersmith",
            "status": "running",
            "phase": "parse-request",
            "created_at": utcnow(),
            "request": spec.to_dict(),
            "request_hash": hash_json(spec.to_dict()),
            "blocking_reason": None,
        }
        state.save()
        state.append_event("run_created", phase="parse-request", status="running")
        return state

    @classmethod
    def load(cls, root: Path) -> "RunState":
        root = root.resolve()
        run_json = root / "run.json"
        if not run_json.is_file():
            raise RuntimeError(f"run not found: {root}")
        state = cls(root)
        state.data = json.loads(run_json.read_text(encoding="utf-8"))
        return state

    # -- lock ---------------------------------------------------------------
    def acquire_lock(self) -> None:
        """Take an advisory lock the kernel releases if this process dies.

        A batch run is long and its containers get killed (OOM, timeout, docker
        stop). An exclusive-create lock file would survive that and wedge the
        run permanently, so the lock is an flock: it disappears with the
        process, whether or not the process got to clean up.
        """
        lock = self.root / ".lock"
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            holder = ""
            try:
                holder = lock.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            # The recorded pid is namespace-local: a run started in a container
            # writes the pid it sees there, which means nothing on the host. It
            # is a breadcrumb only. Whether the lock is actually held is decided
            # by the flock above, which the kernel releases when the holder dies.
            raise RunLocked(
                f"run is already locked: {self.root}"
                + (f" (holder recorded pid {holder}, possibly namespace-local)" if holder else "")
            )
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        self._lock_fd = fd

    def release_lock(self) -> None:
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None
            (self.root / ".lock").unlink(missing_ok=True)

    # -- persistence --------------------------------------------------------
    def save(self) -> None:
        path = self.root / "run.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)

    def append_event(self, kind: str, **data: object) -> None:
        record = {"time": utcnow(), "event": kind, **data}
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -- stages -------------------------------------------------------------
    def stage_dir(self, name: str) -> Path:
        if name not in STAGE_DIRS:
            raise ValueError(f"unknown stage: {name}")
        return self.root / "stages" / name

    def record_stage(self, name: str, result: dict) -> None:
        result = {"recorded_at": utcnow(), **result}
        path = self.stage_dir(name) / "manifest.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
        self.append_event("stage_recorded", stage=name, status=result.get("status"))
