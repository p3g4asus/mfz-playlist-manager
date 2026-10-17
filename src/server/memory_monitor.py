"""Low overhead, periodic memory and application-state sampling."""

import asyncio
import csv
import logging
import os
import sys
import threading
import tracemalloc
from datetime import datetime
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


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

    def __init__(self, path, interval=300, trace_python=False):
        self.path = Path(path)
        self.interval = max(10, interval)
        self.trace_python = trace_python
        self._file = None
        self._writer = None

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

    async def run(self, loop):
        if self.trace_python and not tracemalloc.is_tracing():
            tracemalloc.start()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if self._file.tell() == 0:
            self._writer.writerow(self.FIELDS)
            self._file.flush()
        _LOGGER.info("Memory monitoring enabled: CSV=%s interval=%ss tracemalloc=%s",
                     self.path.resolve(), self.interval, self.trace_python)
        try:
            while True:
                try:
                    self._write_sample(loop)
                except Exception:
                    _LOGGER.exception("Memory monitoring sample failed")
                await asyncio.sleep(self.interval)
        finally:
            self._file.close()

