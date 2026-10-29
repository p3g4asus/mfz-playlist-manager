"""Low overhead, periodic memory and application-state sampling."""

import asyncio
import csv
import logging
import os
import sys
import threading
import time
import tracemalloc
from datetime import datetime
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


def allocation_diff_records(before, after, limit=20):
    """Format allocation deltas, retaining each tracemalloc frame for each site."""
    stats = after.compare_to(before, "lineno")
    return [
        {
            "allocation_location": str(stat.traceback[0]),
            # tracemalloc.Frame is not a traceback.FrameSummary, so
            # traceback.format_list() cannot format it directly.
            "allocation_traceback": "".join(
                f'  File "{frame.filename}", line {frame.lineno}\n'
                for frame in stat.traceback
            ),
            "allocation_size_diff_bytes": stat.size_diff,
            "allocation_count_diff": stat.count_diff,
        }
        for stat in stats[:limit]
    ]


def _process_memory_bytes():
    """Return current RSS and virtual size, or None when unavailable."""
    if sys.platform.startswith("linux"):
        try:
            values = {}
            with open("/proc/self/status", encoding="ascii") as status:
                for line in status:
                    if line.startswith(("VmRSS:", "VmSize:")):
                        key, value = line.split(":", 1)
                        values[key] = int(value.strip().split()[0]) * 1024
            return values.get("VmRSS"), values.get("VmSize")
        except (OSError, ValueError):
            return None, None

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("Psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                                    ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                                                    wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            handle = kernel32.GetCurrentProcess()
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None, None
            return counters.WorkingSetSize, counters.PagefileUsage
        except (AttributeError, OSError):
            return None, None

    # macOS/BSD fallback: resource reports peak RSS, rather than current RSS.
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            peak_bytes = peak
        else:
            peak_bytes = peak * 1024
        return peak_bytes, None
    except (ImportError, OSError, ValueError):
        return None, None


def _cache_counts():
    try:
        from server.telegram.cache import _PLAYLIST_CACHE

        playlists = sum(len(per_user) for per_user in _PLAYLIST_CACHE.values())
        items = sum(len(playlist.items)
                    for per_user in _PLAYLIST_CACHE.values()
                    for playlist in per_user.values())
        return len(_PLAYLIST_CACHE), playlists, items
    except Exception:
        _LOGGER.debug("Could not read Telegram playlist cache counts", exc_info=True)
        return None, None, None


class MemoryMonitor:
    FIELDS = ("timestamp", "rss_bytes", "virtual_bytes", "python_current_bytes",
              "python_peak_bytes", "asyncio_tasks", "threads", "cache_users",
              "cached_playlists", "cached_items")

    SNAPSHOT_FIELDS = (
        "period_start", "period_end", "period_seconds", "python_current_bytes",
        "allocation_location", "allocation_traceback", "allocation_size_diff_bytes",
        "allocation_count_diff",
    )

    def __init__(self, path, interval=300, trace_python=False,
                 snapshot_interval=0, snapshot_path=None, traceback_frames=1):
        self.path = Path(path)
        self.interval = max(10, interval)
        self.snapshot_interval = max(0, snapshot_interval)
        self.snapshot_path = Path(snapshot_path) if snapshot_path else self.path.with_name("memory-allocation-diffs.csv")
        self.trace_python = trace_python or self.snapshot_interval > 0
        self.traceback_frames = max(1, min(25, traceback_frames))
        self._file = None
        self._writer = None
        self._snapshot_file = None
        self._snapshot_writer = None
        self._snapshot = None
        self._snapshot_time = None
        self._snapshot_timestamp = None

    def _write_sample(self, loop):
        rss, virtual = _process_memory_bytes()
        if self.trace_python and tracemalloc.is_tracing():
            py_current, py_peak = tracemalloc.get_traced_memory()
        else:
            py_current, py_peak = None, None
        users, playlists, items = _cache_counts()
        sample = (datetime.now().astimezone().isoformat(timespec="seconds"), rss,
                  virtual, py_current, py_peak, len(asyncio.all_tasks(loop)),
                  threading.active_count(), users, playlists, items)
        self._writer.writerow(sample)
        self._file.flush()
        _LOGGER.info("Memory sample: RSS=%s virtual=%s Python=%s tasks=%d threads=%d cache=%s/%s/%s",
                     rss, virtual, py_current, sample[5], sample[6], users, playlists, items)

    def _write_allocation_diffs_if_due(self):
        if not self.snapshot_interval or self._snapshot is None:
            return
        now = time.monotonic()
        if now - self._snapshot_time < self.snapshot_interval:
            return
        try:
            after = tracemalloc.take_snapshot()
            records = allocation_diff_records(self._snapshot, after)
            period_end = datetime.now().astimezone().isoformat(timespec="seconds")
            period_seconds = round(now - self._snapshot_time, 1)
            old_snapshot = self._snapshot
            self._snapshot = after
            self._snapshot_time = now
            self._snapshot_timestamp = period_end
            del old_snapshot
            current_bytes = tracemalloc.get_traced_memory()[0]
            for record in records:
                self._snapshot_writer.writerow({
                    "period_start": self._previous_snapshot_timestamp,
                    "period_end": period_end,
                    "period_seconds": period_seconds,
                    "python_current_bytes": current_bytes,
                    **record,
                })
            self._snapshot_file.flush()
            self._previous_snapshot_timestamp = period_end
        except Exception:
            _LOGGER.exception("Periodic tracemalloc snapshot comparison failed")

    async def run(self, loop):
        if self.trace_python and not tracemalloc.is_tracing():
            tracemalloc.start(self.traceback_frames)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if self._file.tell() == 0:
            self._writer.writerow(self.FIELDS)
            self._file.flush()
        if self.snapshot_interval:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self._snapshot_file = self.snapshot_path.open("a", newline="", encoding="utf-8")
            self._snapshot_writer = csv.DictWriter(self._snapshot_file,
                                                  fieldnames=self.SNAPSHOT_FIELDS)
            if self._snapshot_file.tell() == 0:
                self._snapshot_writer.writeheader()
                self._snapshot_file.flush()
            self._snapshot = tracemalloc.take_snapshot()
            self._snapshot_time = time.monotonic()
            self._snapshot_timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            self._previous_snapshot_timestamp = self._snapshot_timestamp
        _LOGGER.info("Memory monitoring enabled: CSV=%s interval=%ss tracemalloc=%s snapshot_interval=%ss",
                     self.path.resolve(), self.interval, self.trace_python, self.snapshot_interval)
        try:
            while True:
                try:
                    self._write_sample(loop)
                    self._write_allocation_diffs_if_due()
                except Exception:
                    _LOGGER.exception("Memory monitoring sample failed")
                await asyncio.sleep(self.interval)
        finally:
            self._file.close()
            self._snapshot = None
            if self._snapshot_file:
                self._snapshot_file.close()

