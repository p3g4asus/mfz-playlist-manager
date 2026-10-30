"""Opt-in asyncio task and WebSocket lifecycle diagnostics."""

import asyncio
import csv
import hashlib
import logging
import time
import uuid
import weakref
from datetime import datetime
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _task_coro_name(task):
    coro = task.get_coro()
    name = getattr(coro, "__qualname__", type(coro).__name__)
    module = getattr(coro, "__module__", "")
    return f"{module}.{name}" if module else name


def _task_stack(task, limit=5):
    frames = task.get_stack(limit=limit)
    return "\n".join(
        f'{frame.f_code.co_filename}:{frame.f_lineno} in {frame.f_code.co_name}'
        for frame in frames
    )


class TaskDiagnostics:
    TASK_FIELDS = (
        "timestamp", "task_id", "task_name", "coroutine", "state",
        "first_seen", "observed_age_seconds", "current_stack",
    )
    WEBSOCKET_FIELDS = (
        "timestamp", "event", "connection_id", "kind", "client_fingerprint",
        "identity_source", "peer", "user_agent", "task_id", "task_name",
        "elapsed_seconds", "closed", "close_code", "exception",
    )

    def __init__(self, task_path, websocket_path, interval=300):
        self.task_path = Path(task_path)
        self.websocket_path = Path(websocket_path)
        self.interval = max(30, interval)
        self._task_file = None
        self._task_writer = None
        self._websocket_file = None
        self._websocket_writer = None
        self._first_seen = weakref.WeakKeyDictionary()
        self._connections = {}

    @staticmethod
    def _open_csv(path, fields):
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists() or path.stat().st_size == 0
        if not is_new:
            with path.open("r", newline="", encoding="utf-8") as existing:
                old_fields = next(csv.reader(existing), [])
            if old_fields != list(fields):
                old_path = path
                version = 2
                while True:
                    path = old_path.with_name(f"{old_path.stem}-v{version}{old_path.suffix}")
                    if not path.exists() or path.stat().st_size == 0:
                        break
                    with path.open("r", newline="", encoding="utf-8") as existing:
                        if next(csv.reader(existing), []) == list(fields):
                            break
                    version += 1
                is_new = not path.exists() or path.stat().st_size == 0
                _LOGGER.warning("Task diagnostics schema changed; writing to %s instead of %s",
                                path, old_path)
        file = path.open("a", newline="", encoding="utf-8")
        writer = csv.DictWriter(file, fieldnames=fields)
        if is_new:
            writer.writeheader()
            file.flush()
        return file, writer, path

    def _ensure_task_writer(self):
        if self._task_file is None:
            self._task_file, self._task_writer, self.task_path = self._open_csv(
                self.task_path, self.TASK_FIELDS
            )

    def _ensure_websocket_writer(self):
        if self._websocket_file is None:
            self._websocket_file, self._websocket_writer, self.websocket_path = self._open_csv(
                self.websocket_path, self.WEBSOCKET_FIELDS
            )

    def sample_tasks(self, loop):
        now_mono = time.monotonic()
        timestamp = _now()
        current = asyncio.current_task(loop=loop)
        tasks = sorted(asyncio.all_tasks(loop), key=lambda task: (task.get_name(), id(task)))
        self._ensure_task_writer()
        for task in tasks:
            if task is current or task.done():
                continue
            first_seen = self._first_seen.get(task)
            if first_seen is None:
                first_seen = (now_mono, timestamp)
                self._first_seen[task] = first_seen
            first_seen_mono, first_seen_timestamp = first_seen
            self._task_writer.writerow({
                "timestamp": timestamp,
                "task_id": hex(id(task)),
                "task_name": task.get_name(),
                "coroutine": _task_coro_name(task),
                "state": "cancelling" if task.cancelling() else "pending",
                "first_seen": first_seen_timestamp,
                "observed_age_seconds": round(now_mono - first_seen_mono, 1),
                "current_stack": _task_stack(task),
            })
        self._task_file.flush()

    def websocket_opened(self, request, kind, identity=None, identity_source=""):
        connection_id = uuid.uuid4().hex
        task = asyncio.current_task()
        user_agent = request.headers.get("User-Agent", "").replace("\r", " ").replace("\n", " ")[:200]
        peer = request.remote or ""
        if identity:
            fingerprint_source = identity_source or "client_key"
            fingerprint_material = f"{kind}:{fingerprint_source}:{identity}"
        else:
            fingerprint_source = "peer_user_agent"
            fingerprint_material = f"{kind}:{fingerprint_source}:{peer}:{user_agent}"
        client_fingerprint = hashlib.sha256(fingerprint_material.encode("utf-8")).hexdigest()[:16]
        self._ensure_websocket_writer()
        self._websocket_writer.writerow({
            "timestamp": _now(),
            "event": "open",
            "connection_id": connection_id,
            "kind": kind,
            "client_fingerprint": client_fingerprint,
            "identity_source": fingerprint_source,
            "peer": peer,
            "user_agent": user_agent,
            "task_id": hex(id(task)) if task else "",
            "task_name": task.get_name() if task else "",
        })
        self._websocket_file.flush()
        self._connections[connection_id] = {
            "started": time.monotonic(),
            "kind": kind,
            "client_fingerprint": client_fingerprint,
            "identity_source": fingerprint_source,
            "peer": peer,
            "user_agent": user_agent,
        }
        return connection_id

    def websocket_closed(self, connection_id, kind, ws, exception=None):
        connection = self._connections.pop(connection_id, {})
        task = asyncio.current_task()
        ws_exception = exception or ws.exception()
        self._ensure_websocket_writer()
        self._websocket_writer.writerow({
            "timestamp": _now(),
            "event": "close",
            "connection_id": connection_id,
            "kind": kind,
            "client_fingerprint": connection.get("client_fingerprint", ""),
            "identity_source": connection.get("identity_source", ""),
            "peer": connection.get("peer", ""),
            "user_agent": connection.get("user_agent", ""),
            "task_id": hex(id(task)) if task else "",
            "task_name": task.get_name() if task else "",
            "elapsed_seconds": round(time.monotonic() - connection.get("started", time.monotonic()), 3),
            "closed": ws.closed,
            "close_code": ws.close_code or "",
            "exception": repr(ws_exception) if ws_exception else "",
        })
        self._websocket_file.flush()

    async def run(self, loop):
        _LOGGER.info("Asyncio task diagnostics enabled: tasks=%s websockets=%s interval=%ss",
                     self.task_path.resolve(), self.websocket_path.resolve(), self.interval)
        try:
            while True:
                try:
                    self.sample_tasks(loop)
                except Exception:
                    _LOGGER.exception("Asyncio task census failed")
                await asyncio.sleep(self.interval)
        finally:
            self.close()

    def close(self):
        if self._task_file:
            self._task_file.close()
            self._task_file = None
            self._task_writer = None
        if self._websocket_file:
            self._websocket_file.close()
            self._websocket_file = None
            self._websocket_writer = None
