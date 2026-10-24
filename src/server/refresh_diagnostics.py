"""CSV diagnostics for scheduled playlist refreshes."""

import asyncio
import csv
import json
import logging
import threading
import time
import tracemalloc
import uuid
from datetime import datetime
from pathlib import Path

from server.memory_monitor import _cache_counts, _process_memory_bytes

_LOGGER = logging.getLogger(__name__)


class RefreshDiagnostics:
    FIELDS = (
        "run_id", "timestamp", "event", "processor", "playlist_id", "user_id",
        "autoupdate", "elapsed_seconds", "outcome", "rss_bytes", "rss_delta_bytes",
        "virtual_bytes", "python_current_bytes", "python_delta_bytes", "asyncio_tasks",
        "task_delta", "asyncio_task_types", "threads", "cache_users", "cached_playlists", "cached_items",
        "allocation_location", "allocation_size_diff_bytes", "allocation_count_diff",
    )

    def __init__(self, path, allocation_snapshots=False):
        self.path = Path(path)
        self.allocation_snapshots = allocation_snapshots
        self._file = None
        self._writer = None
        self._snapshot_before = None
        self._started_tracemalloc = False

    def _open(self):
        if self._file is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            is_new = not self.path.exists() or self.path.stat().st_size == 0
            self._file = self.path.open("a", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDS)
            if is_new:
                self._writer.writeheader()
                self._file.flush()

    @staticmethod
    def _sample():
        rss, virtual = _process_memory_bytes()
        python_current = tracemalloc.get_traced_memory()[0] if tracemalloc.is_tracing() else None
        try:
            tasks = asyncio.all_tasks()
            task_count = len(tasks)
        except RuntimeError:
            tasks = ()
            task_count = None
        task_types = {}
        for task in tasks:
            coro = task.get_coro()
            coro_name = getattr(coro, "__qualname__", type(coro).__name__)
            coro_module = getattr(coro, "__module__", "")
            name = f"{coro_module}.{coro_name}" if coro_module else coro_name
            task_types[name] = task_types.get(name, 0) + 1
        users, playlists, items = _cache_counts()
        return {
            "rss_bytes": rss,
            "virtual_bytes": virtual,
            "python_current_bytes": python_current,
            "asyncio_tasks": task_count,
            "asyncio_task_types": json.dumps(task_types, sort_keys=True, separators=(",", ":")),
            "threads": threading.active_count(),
            "cache_users": users,
            "cached_playlists": playlists,
            "cached_items": items,
        }

    def _write(self, run_id, event, processor="", playlist=None, started=None,
               before=None, outcome="", **extra):
        try:
            sample = self._sample()
            record = {
                "run_id": run_id,
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "event": event,
                "processor": processor,
                "playlist_id": getattr(playlist, "rowid", ""),
                "user_id": getattr(playlist, "useri", ""),
                "autoupdate": getattr(playlist, "autoupdate", ""),
                "elapsed_seconds": round(time.monotonic() - started, 3) if started else "",
                "outcome": outcome,
                **sample,
                **extra,
            }
            if before:
                for field, delta_field in (("rss_bytes", "rss_delta_bytes"),
                                           ("python_current_bytes", "python_delta_bytes"),
                                           ("asyncio_tasks", "task_delta")):
                    old, current = before.get(field), sample.get(field)
                    record[delta_field] = current - old if old is not None and current is not None else ""
            self._open()
            self._writer.writerow(record)
            self._file.flush()
        except Exception:
            _LOGGER.exception("Could not write refresh diagnostic row")

    def start_run(self):
        run_id = uuid.uuid4().hex
        self._snapshot_before = None
        self._started_tracemalloc = False
        if self.allocation_snapshots:
            if not tracemalloc.is_tracing():
                tracemalloc.start(10)
                self._started_tracemalloc = True
            try:
                self._snapshot_before = tracemalloc.take_snapshot()
            except Exception:
                _LOGGER.exception("Could not take tracemalloc snapshot before refresh")
        self._write(run_id, "run_start")
        return run_id

    def end_run(self, run_id, started, outcome):
        try:
            if self.allocation_snapshots and self._snapshot_before is not None:
                after = tracemalloc.take_snapshot()
                stats = after.compare_to(self._snapshot_before, "lineno")
                for stat in stats[:20]:
                    self._write(
                        run_id, "allocation_diff", outcome=outcome,
                        allocation_location=str(stat.traceback[0]),
                        allocation_size_diff_bytes=stat.size_diff,
                        allocation_count_diff=stat.count_diff,
                    )
        except Exception:
            _LOGGER.exception("Could not compare tracemalloc snapshots after refresh")
        finally:
            self._snapshot_before = None
            if self._started_tracemalloc:
                tracemalloc.stop()
                self._started_tracemalloc = False
            self._write(run_id, "run_end", started=started, outcome=outcome)

    def start_processor(self, run_id, processor):
        started = time.monotonic()
        before = self._sample()
        self._write(run_id, "processor_start", processor=processor)
        return started, before

    def end_processor(self, run_id, processor, token, outcome):
        started, before = token
        self._write(run_id, "processor_end", processor=processor, started=started,
                    before=before, outcome=outcome)

    def start_playlist(self, run_id, processor, playlist):
        started = time.monotonic()
        before = self._sample()
        self._write(run_id, "playlist_start", processor=processor, playlist=playlist)
        return started, before

    def end_playlist(self, run_id, processor, playlist, token, outcome):
        started, before = token
        self._write(run_id, "playlist_end", processor=processor, playlist=playlist,
                    started=started, before=before, outcome=outcome)

    def close(self):
        if self._file:
            self._file.close()
            self._file = None
            self._writer = None
