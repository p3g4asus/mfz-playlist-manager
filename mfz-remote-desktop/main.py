"""MFZ Remote Desktop - minimal remote-command client using asyncio."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import json
import os
import queue
import re
import shlex
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

try:
    import pystray
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    pystray = None

URL_PATTERN = re.compile(
    r"https://([^/]+)/([^-]+)-s/play/player_remote_commands\.htm\?hex=([a-f0-9]+)"
)
RECONNECT_SECONDS = 10
PING_SECONDS = 10
PING_TIMEOUT_SECONDS = 3
PUSH_RESPONSE_TIMEOUT_SECONDS = 3
NOT_IMPLEMENTED = 501
SETTINGS_DIRECTORY = Path.cwd()


def websocket_url(remote_url: str) -> str | None:
    """Convert an MFZ remote-command URL into its WebSocket endpoint."""
    match = URL_PATTERN.search(remote_url.strip())
    if not match:
        return None
    return f"wss://{match.group(1)}/{match.group(2)}-ws/j{match.group(3)}"


def settings_path() -> Path:
    return SETTINGS_DIRECTORY / ".mfz-remote-desktop.json"


def configure_settings_directory(directory: str | Path) -> None:
    """Select the directory containing the persistent settings file."""
    global SETTINGS_DIRECTORY
    SETTINGS_DIRECTORY = Path(directory).expanduser().resolve()
    SETTINGS_DIRECTORY.mkdir(parents=True, exist_ok=True)


def load_url() -> str:
    try:
        value = load_config().get("remote_url", "")
        return value if isinstance(value, str) else ""
    except (OSError, json.JSONDecodeError):
        return ""


def save_url(remote_url: str) -> None:
    config = load_config()
    config["remote_url"] = remote_url
    save_config(config)


def load_config() -> dict[str, Any]:
    try:
        config = json.loads(settings_path().read_text(encoding="utf-8"))
        return config if isinstance(config, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config: dict[str, Any]) -> None:
    try:
        settings_path().write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def new_log_path() -> Path:
    configured_directory = load_config().get("log_directory")
    if isinstance(configured_directory, str) and configured_directory.strip():
        directory = Path(configured_directory).expanduser()
        if not directory.is_absolute():
            directory = SETTINGS_DIRECTORY / directory
    else:
        directory = Path.cwd() / "log"
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    return directory / f"mfz-remote-desktop_{stamp}.log"


def create_app_icon() -> Any:
    """Create a compact desktop-monitor icon inspired by U+1F5A5 (🖥)."""
    image = Image.new("RGB", (64, 64), "#1f2937")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((7, 9, 57, 44), radius=5, fill="#e5e7eb")
    draw.rounded_rectangle((10, 12, 54, 40), radius=2, fill="#0f172a")
    draw.rectangle((13, 15, 51, 37), fill="#2563eb")
    draw.rectangle((13, 31, 51, 37), fill="#1d4ed8")
    draw.rectangle((27, 44, 37, 51), fill="#e5e7eb")
    draw.rounded_rectangle((19, 51, 45, 55), radius=2, fill="#e5e7eb")
    draw.ellipse((45, 17, 49, 21), fill="#86efac")
    return image


def close_on_escape(window: tk.Misc, close_action: Callable[[], None]) -> None:
    """Make Escape perform the exact same action as the window close button."""
    window.protocol("WM_DELETE_WINDOW", close_action)
    window.bind("<Escape>", lambda _: close_action())


def activate_window(window: tk.Toplevel) -> None:
    """Raise a newly-created dialog and give it keyboard focus."""
    def activate() -> None:
        window.lift()
        window.focus_force()
    window.after(0, activate)


class CommandHandler:
    """Extension point for ``cmd: remd`` commands, selected by ``sub``."""

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[dict[str, Any]], int]] = {}

    def execute(self, message: dict[str, Any]) -> int:
        if message.get("cmd") != "remd":
            return NOT_IMPLEMENTED
        subcommand = message.get("sub")
        handler = self.handlers.get(subcommand) if isinstance(subcommand, str) else None
        if handler is None:
            return NOT_IMPLEMENTED
        try:
            return int(handler(message))
        except Exception:
            return 500


class CommandStore:
    """Thread-safe persistent definitions of user commands."""

    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._on_change = on_change
        raw_commands = load_config().get("commands", [])
        self._commands: dict[str, dict[str, Any]] = {}
        if isinstance(raw_commands, list):
            for command in raw_commands:
                if self._valid(command):
                    self._commands[command["name"]] = command

    @staticmethod
    def _valid(command: Any) -> bool:
        return (
            isinstance(command, dict)
            and isinstance(command.get("name"), str)
            and bool(command["name"])
            and isinstance(command.get("type"), str)
            and isinstance(command.get("parameters"), list)
        )

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(command, parameters=[dict(p) for p in command["parameters"]]) for command in self._commands.values()]

    def get(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            command = self._commands.get(name)
            return dict(command, parameters=[dict(p) for p in command["parameters"]]) if command else None

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._commands)

    def replace(self, old_name: str | None, command: dict[str, Any]) -> None:
        if not self._valid(command):
            raise ValueError("Definizione comando non valida")
        with self._lock:
            if old_name and old_name != command["name"]:
                self._commands.pop(old_name, None)
            self._commands[command["name"]] = command
            self._save_locked()
        if self._on_change:
            self._on_change()

    def delete(self, name: str) -> None:
        with self._lock:
            self._commands.pop(name, None)
            self._save_locked()
        if self._on_change:
            self._on_change()

    def _save_locked(self) -> None:
        config = load_config()
        config["commands"] = list(self._commands.values())
        save_config(config)


@dataclass
class ConnectionEvent:
    kind: str
    text: str


class PingTimeout(Exception):
    pass


class RemoteConnection:
    """Runs every WebSocket operation and timer as asyncio coroutines."""

    def __init__(self, events: queue.Queue[ConnectionEvent]) -> None:
        self.events = events
        self._loop = asyncio.new_event_loop()
        self._session_task: asyncio.Task[None] | None = None
        self._ping_response = asyncio.Event()
        self._push_waiter: asyncio.Future[Any] | None = None
        self._push_lock = asyncio.Lock()
        self._ws: Any | None = None
        self.commands = CommandStore(self._command_list_changed)
        self._manual_stop = True
        self._log_path: Path | None = None
        self._thread = threading.Thread(target=self._run_loop, name="mfz-asyncio", daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        self._loop.close()

    def start(self, remote_url: str, log_path: Path) -> bool:
        remote_url = remote_url.strip()
        if not websocket_url(remote_url):
            self._event("log", "URL non valido: collegamento non avviato.")
            self._event("state", "idle")
            return False
        save_url(remote_url)
        asyncio.run_coroutine_threadsafe(self._begin(remote_url, log_path), self._loop)
        return True

    def disconnect(self) -> None:
        asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)

    def stop(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        with contextlib.suppress(Exception):
            future.result(timeout=3)
        self._thread.join(timeout=3)

    def _event(self, kind: str, text: str) -> None:
        self.events.put(ConnectionEvent(kind, text))

    def _log(self, text: str) -> None:
        stamped = f"{time.strftime('%H:%M:%S')}  {text}"
        if self._log_path:
            try:
                with self._log_path.open("a", encoding="utf-8") as output:
                    output.write(stamped + "\n")
            except OSError:
                pass
        self._event("log", text)

    def _set_state(self, state: str) -> None:
        self._event("state", state)

    def _command_list_changed(self) -> None:
        """Schedule an announcement when commands are edited from the GUI thread."""
        try:
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._push_current_commands()))
        except RuntimeError:
            pass

    async def _cancel_session(self) -> None:
        task = self._session_task
        self._session_task = None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _begin(self, remote_url: str, log_path: Path) -> None:
        self._manual_stop = True
        await self._cancel_session()
        self._log_path = log_path
        self._manual_stop = False
        self._log(f"Connect premuto. Log della sessione: {log_path}")
        self._session_task = asyncio.create_task(self._connection_loop(remote_url))

    async def _disconnect(self) -> None:
        self._manual_stop = True
        await self._cancel_session()
        self._log("Disconnessione richiesta dall'utente.")
        self._set_state("idle")

    async def _shutdown(self) -> None:
        await self._disconnect()
        self._loop.call_soon(self._loop.stop)

    async def _connection_loop(self, remote_url: str) -> None:
        endpoint = websocket_url(remote_url)
        assert endpoint is not None
        try:
            while not self._manual_stop:
                self._set_state("trying")
                self._log(f"Tentativo di connessione a {endpoint}.")
                try:
                    async with connect(endpoint, ping_interval=None) as ws:
                        save_url(remote_url)
                        self._set_state("connected")
                        self._ws = ws
                        self._log("WebSocket connesso.")
                        try:
                            await self._run_connected(ws)
                        finally:
                            if self._ws is ws:
                                self._ws = None
                        self._log("WebSocket disconnesso.")
                except PingTimeout:
                    self._log("Ping senza risposta entro 3 secondi: disconnessione.")
                except ConnectionClosed as exc:
                    self._log(f"WebSocket disconnesso ({exc}).")
                except OSError as exc:
                    self._log(f"Connessione non riuscita: {exc}.")
                except Exception as exc:
                    self._log(f"Errore WebSocket: {exc}.")
                if not self._manual_stop:
                    self._set_state("trying")
                    self._log("Nuovo tentativo di connessione fra 10 secondi.")
                    await asyncio.sleep(RECONNECT_SECONDS)
        except asyncio.CancelledError:
            raise
        finally:
            if self._manual_stop:
                self._set_state("idle")

    async def _run_connected(self, ws: Any) -> None:
        receiver = asyncio.create_task(self._receive_messages(ws))
        try:
            approved = await self._announce_until_approved(ws, receiver)
            if not approved:
                return
            self._log("Lista comandi accettata: pronto a ricevere comandi.")
            heartbeat = asyncio.create_task(self._heartbeat(ws))
            done, pending = await asyncio.wait({receiver, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in pending:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            for task in done:
                task.result()
        finally:
            if not receiver.done():
                receiver.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await receiver

    async def _announce_until_approved(self, ws: Any, receiver: asyncio.Task[None]) -> bool:
        while not self._manual_stop and not receiver.done():
            if await self._push_current_commands(ws, wait_for_response=True):
                return True
            self._log("Lista comandi non confermata: nuovo invio fra 10 secondi.")
            try:
                await asyncio.wait_for(asyncio.shield(receiver), timeout=RECONNECT_SECONDS)
            except asyncio.TimeoutError:
                continue
            return False
        return False

    async def _push_current_commands(self, ws: Any | None = None, wait_for_response: bool = False) -> bool:
        ws = ws or self._ws
        if ws is None:
            return False
        async with self._push_lock:
            waiter = self._loop.create_future()
            self._push_waiter = waiter
            await self._send(ws, {"cmd": "remotepush", "what": "commands", "commands": self.commands.names()})
            if not wait_for_response:
                return True
            try:
                rv = await asyncio.wait_for(waiter, timeout=PUSH_RESPONSE_TIMEOUT_SECONDS)
                if rv == 0:
                    return True
                self._log(f"remotepush rifiutato dal server (rv={rv}).")
                return False
            except asyncio.TimeoutError:
                self._log("Nessuna risposta a remotepush entro 3 secondi.")
                return False
            finally:
                if self._push_waiter is waiter:
                    self._push_waiter = None

    async def _heartbeat(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(PING_SECONDS)
            self._ping_response.clear()
            await self._send(ws, {"cmd": "remoteping", "t": time.time()})
            try:
                await asyncio.wait_for(self._ping_response.wait(), timeout=PING_TIMEOUT_SECONDS)
            except asyncio.TimeoutError as exc:
                raise PingTimeout from exc

    async def _receive_messages(self, ws: Any) -> None:
        async for raw in ws:
            self._log(f"Ricevuto: {raw}")
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                self._log("Messaggio JSON non valido ignorato.")
                continue
            if not isinstance(message, dict) or not isinstance(message.get("cmd"), str):
                self._log("Messaggio senza cmd valido ignorato.")
                continue
            if message["cmd"] == "remotepush" and "rv" in message:
                if self._push_waiter and not self._push_waiter.done():
                    self._push_waiter.set_result(message["rv"])
                continue
            if message["cmd"] == "remoteping":
                self._ping_response.set()
                continue
            if "__id" not in message:
                self._log("Messaggio senza __id: nessuna risposta inviata.")
                continue
            rv, additional_fields = await self._handle_command(message)
            response = {
                "cmd": "remote",
                "__id": message["__id"],
                "sub": message.get("sub"),
                "rv": rv,
                **additional_fields,
            }
            await self._send(ws, response)

    async def _send(self, ws: Any, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        await ws.send(encoded)
        self._log(f"Inviato: {encoded}")

    async def _handle_command(self, message: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Execute a ``remd`` subcommand and return its result and extra fields."""
        if message.get("cmd") != "remd":
            return NOT_IMPLEMENTED, {}
        subcommand = message.get("sub")
        if not isinstance(subcommand, str):
            return NOT_IMPLEMENTED, {}
        if subcommand == "__list":
            return 0, {"commands": self.commands.names()}
        command = self.commands.get(subcommand)
        if command is None:
            self._log(f"Sottocomando remd sconosciuto: {subcommand}.")
            return NOT_IMPLEMENTED, {}
        if command["type"] == "launch":
            return await self._launch(command), {}
        return NOT_IMPLEMENTED, {}

    async def _launch(self, command: dict[str, Any]) -> int:
        parameters = {item.get("name"): item.get("value") for item in command["parameters"] if isinstance(item, dict)}
        executable = parameters.get("exe")
        if not isinstance(executable, str) or not executable.strip():
            self._log(f"Comando {command['name']}: parametro exe mancante.")
            return 400
        line = parameters.get("line", "")
        directory = parameters.get("dir", "")
        if not isinstance(line, str) or not isinstance(directory, str):
            self._log(f"Comando {command['name']}: parametri launch non validi.")
            return 400
        try:
            if os.name == "nt":
                # Preserve the exact command-line syntax entered by the user for cmd.exe.
                target_command = subprocess.list2cmdline([executable]) + (f" {line}" if line else "")
                self._log(f"Avvio launch {command['name']}: cwd={directory or os.getcwd()}; comando={target_command}")
                detached_flags = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                )
                breakaway_flag = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
                try:
                    process = await asyncio.create_subprocess_shell(
                        target_command, cwd=directory or None,
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                        creationflags=detached_flags | breakaway_flag,
                    )
                except OSError as exc:
                    if not breakaway_flag:
                        raise
                    self._log(f"Breakaway dal job non disponibile ({exc}); avvio detached standard.")
                    process = await asyncio.create_subprocess_shell(
                        target_command, cwd=directory or None,
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                        creationflags=detached_flags,
                    )
            else:
                arguments = shlex.split(line) if line else []
                command_line = shlex.join([executable, *arguments])
                self._log(f"Avvio launch {command['name']}: cwd={directory or os.getcwd()}; comando={command_line}")
                process = await asyncio.create_subprocess_exec(
                    executable, *arguments, cwd=directory or None,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
            self._log(f"Comando launch {command['name']} avviato (pid {process.pid}).")
            return 0
        except (OSError, ValueError) as exc:
            self._log(f"Avvio comando {command['name']} non riuscito: {exc}.")
            return 500


class Application:
    def __init__(self, start_minimized: bool = False) -> None:
        if os.name == "nt":
            # Prevent Windows from grouping this Tk window under python.exe.
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mfz.remote.desktop")
        self.root = tk.Tk()
        self.root.title("MFZ Remote Desktop")
        self.root.minsize(640, 360)
        if start_minimized:
            self.root.withdraw()
        self._icon_image = create_app_icon() if pystray is not None else None
        self._window_icon: Any = None
        if self._icon_image is not None:
            self._window_icon = ImageTk.PhotoImage(self._icon_image)
            self.root.iconphoto(True, self._window_icon)
        self.events: queue.Queue[ConnectionEvent] = queue.Queue()
        self.connection = RemoteConnection(self.events)
        self.tray: Any = None
        self.url_var = tk.StringVar(value=load_url())
        self.status_var = tk.StringVar(value="In attesa dell'URL")
        self.connection_state = "idle"
        self._build_ui()
        close_on_escape(self.root, self.hide)
        self.root.after(100, self._drain_events)
        self._install_tray()
        if self.url_var.get() and websocket_url(self.url_var.get()):
            self.connection.start(self.url_var.get(), new_log_path())

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="URL di collegamento").pack(anchor=tk.W)
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=(3, 10))
        self.url_entry = ttk.Entry(row, textvariable=self.url_var)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.connection_button = ttk.Button(row, text="Connect", command=self.connection_action)
        self.connection_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(row, text="Comandi", command=self.show_commands).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(row, text="Nascondi", command=self.hide).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(frame, textvariable=self.status_var).pack(anchor=tk.W, pady=(0, 6))
        self.log = tk.Text(frame, height=15, state=tk.DISABLED, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True)

    def connection_action(self) -> None:
        if self.connection_state in {"trying", "connected"}:
            self.connection.disconnect()
        else:
            self.connection.start(self.url_var.get(), new_log_path())

    def _apply_state(self, state: str) -> None:
        self.connection_state = state
        labels = {"idle": ("Connect", "Disconnesso"), "trying": ("Stop trying", "Tentativo di connessione..."), "connected": ("Disconnect", "Connesso")}
        button_text, status = labels[state]
        self.connection_button.configure(text=button_text)
        self.status_var.set(status)
        self.url_entry.configure(state=tk.NORMAL if state == "idle" else tk.DISABLED)

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event.kind == "state":
                    self._apply_state(event.text)
                else:
                    self.log.configure(state=tk.NORMAL)
                    self.log.insert(tk.END, f"{time.strftime('%H:%M:%S')}  {event.text}\n")
                    self.log.see(tk.END)
                    self.log.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def show_commands(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Comandi remd")
        window.geometry("570x340")
        window.transient(self.root)
        close_on_escape(window, window.destroy)
        activate_window(window)
        tree = ttk.Treeview(window, columns=("name", "type", "parameters"), show="headings")
        tree.heading("name", text="Nome (sub)")
        tree.heading("type", text="Tipo")
        tree.heading("parameters", text="Parametri")
        tree.column("name", width=150)
        tree.column("type", width=100)
        tree.column("parameters", width=290)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for command in self.connection.commands.all():
                parameters = ", ".join(item.get("name", "") for item in command["parameters"])
                tree.insert("", tk.END, iid=command["name"], values=(command["name"], command["type"], parameters))

        def selected() -> str | None:
            return tree.selection()[0] if tree.selection() else None

        def edit_selected(_: Any = None) -> None:
            name = selected()
            if name:
                self.edit_command(name, refresh)

        tree.bind("<Double-1>", edit_selected)

        actions = ttk.Frame(window)
        actions.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(actions, text="Aggiungi", command=lambda: self.edit_command(None, refresh)).pack(side=tk.LEFT)
        ttk.Button(actions, text="Modifica", command=edit_selected).pack(side=tk.LEFT, padx=5)

        def delete() -> None:
            name = selected()
            if name and messagebox.askyesno("Elimina comando", f"Eliminare il comando '{name}'?", parent=window):
                self.connection.commands.delete(name)
                refresh()

        ttk.Button(actions, text="Elimina", command=delete).pack(side=tk.LEFT)
        ttk.Button(actions, text="Chiudi", command=window.destroy).pack(side=tk.RIGHT)
        refresh()

    def edit_command(self, command_name: str | None, refresh: Callable[[], None]) -> None:
        existing = self.connection.commands.get(command_name) if command_name else None
        if command_name and existing is None:
            return
        parameters = [dict(item) for item in existing["parameters"]] if existing else [
            {"name": "exe", "type": "string", "value": ""},
            {"name": "line", "type": "string", "value": ""},
            {"name": "dir", "type": "string", "value": ""},
        ]
        window = tk.Toplevel(self.root)
        window.title("Modifica comando" if existing else "Nuovo comando")
        window.geometry("600x390")
        window.transient(self.root)
        close_on_escape(window, window.destroy)
        activate_window(window)
        content = ttk.Frame(window, padding=10)
        content.pack(fill=tk.BOTH, expand=True)
        name_var = tk.StringVar(value=existing["name"] if existing else "")
        type_var = tk.StringVar(value=existing["type"] if existing else "launch")
        top = ttk.Frame(content)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top, text="Nome (sub)").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(top, textvariable=name_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(top, text="Tipo").grid(row=0, column=2, sticky=tk.W)
        ttk.Combobox(top, textvariable=type_var, values=("launch",), state="readonly", width=14).grid(row=0, column=3, sticky=tk.W, padx=6)
        tree = ttk.Treeview(content, columns=("name", "type", "value"), show="headings")
        for key, title, width in (("name", "Nome", 155), ("type", "Tipo", 110), ("value", "Valore", 290)):
            tree.heading(key, text=title)
            tree.column(key, width=width)
        tree.pack(fill=tk.BOTH, expand=True)

        def redraw() -> None:
            tree.delete(*tree.get_children())
            for index, parameter in enumerate(parameters):
                tree.insert("", tk.END, iid=str(index), values=(parameter["name"], parameter["type"], parameter["value"]))

        def parameter_editor(index: int | None = None) -> None:
            item = parameters[index] if index is not None else {"name": "", "type": "string", "value": ""}
            dialog = tk.Toplevel(window)
            dialog.title("Modifica parametro" if index is not None else "Nuovo parametro")
            dialog.transient(window)
            dialog.grab_set()
            close_on_escape(dialog, dialog.destroy)
            activate_window(dialog)
            body = ttk.Frame(dialog, padding=10)
            body.pack(fill=tk.BOTH, expand=True)
            p_name = tk.StringVar(value=item["name"])
            p_type = tk.StringVar(value=item["type"])
            p_value = tk.StringVar(value=str(item["value"]))
            for row, (label, variable) in enumerate((("Nome", p_name), ("Tipo", p_type), ("Valore", p_value))):
                ttk.Label(body, text=label).grid(row=row, column=0, sticky=tk.W, pady=3)
                if label == "Tipo":
                    ttk.Combobox(body, textvariable=variable, values=("integer", "floating point", "string"), state="readonly").grid(row=row, column=1, sticky=tk.EW, padx=(8, 0), pady=3)
                else:
                    ttk.Entry(body, textvariable=variable, width=38).grid(row=row, column=1, sticky=tk.EW, padx=(8, 0), pady=3)

            def save_parameter() -> None:
                parameter_name = p_name.get().strip()
                parameter_type = p_type.get()
                if not parameter_name or any(p["name"] == parameter_name for pos, p in enumerate(parameters) if pos != index):
                    messagebox.showerror("Parametro", "Il nome del parametro deve essere presente e univoco.", parent=dialog)
                    return
                try:
                    value: Any = int(p_value.get()) if parameter_type == "integer" else float(p_value.get()) if parameter_type == "floating point" else p_value.get()
                except ValueError:
                    messagebox.showerror("Parametro", "Il valore non corrisponde al tipo scelto.", parent=dialog)
                    return
                parameter = {"name": parameter_name, "type": parameter_type, "value": value}
                if index is None:
                    parameters.append(parameter)
                else:
                    parameters[index] = parameter
                redraw()
                dialog.destroy()

            ttk.Button(body, text="Salva", command=save_parameter).grid(row=3, column=1, sticky=tk.E, pady=(8, 0))

        def edit_selected_parameter(_: Any = None) -> None:
            if tree.selection():
                parameter_editor(int(tree.selection()[0]))

        tree.bind("<Double-1>", edit_selected_parameter)

        buttons = ttk.Frame(content)
        buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(buttons, text="Aggiungi parametro", command=parameter_editor).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Modifica parametro", command=edit_selected_parameter).pack(side=tk.LEFT, padx=5)

        def remove_parameter() -> None:
            if tree.selection():
                parameters.pop(int(tree.selection()[0]))
                redraw()

        ttk.Button(buttons, text="Elimina parametro", command=remove_parameter).pack(side=tk.LEFT)

        def save_command() -> None:
            name = name_var.get().strip()
            if not name or name == "__list":
                messagebox.showerror("Comando", "Il nome è obbligatorio e non può essere __list.", parent=window)
                return
            if name != command_name and self.connection.commands.get(name):
                messagebox.showerror("Comando", "Esiste già un comando con questo nome.", parent=window)
                return
            launch_parameters = {item["name"] for item in parameters}
            if type_var.get() == "launch" and not {"exe", "line", "dir"}.issubset(launch_parameters):
                messagebox.showerror("Comando", "Un comando launch richiede exe, line e dir.", parent=window)
                return
            self.connection.commands.replace(command_name, {"name": name, "type": type_var.get(), "parameters": parameters})
            refresh()
            window.destroy()

        ttk.Button(buttons, text="Salva comando", command=save_command).pack(side=tk.RIGHT)
        redraw()

    def hide(self) -> None:
        self.root.withdraw()

    def show(self, _: Any = None) -> None:
        self.root.after(0, self._show_window)

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _install_tray(self) -> None:
        if pystray is None:
            return
        self.tray = pystray.Icon(
            "mfz-remote-desktop", self._icon_image, "MFZ Remote Desktop",
            pystray.Menu(pystray.MenuItem("Mostra", self.show), pystray.MenuItem("Esci", self.quit)),
        )
        threading.Thread(target=self.tray.run, name="mfz-tray", daemon=True).start()

    def quit(self, _: Any = None) -> None:
        self.root.after(0, self._quit_application)

    def _quit_application(self) -> None:
        self.connection.stop()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MFZ Remote Desktop")
    parser.add_argument("--minimized", action="store_true", help="avvia nascosto nell'area di notifica")
    parser.add_argument("--config-dir", default=Path.cwd(), help="cartella del file .mfz-remote-desktop.json")
    arguments = parser.parse_args()
    configure_settings_directory(arguments.config_dir)
    Application(start_minimized=arguments.minimized).run()
