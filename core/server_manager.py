"""Manages the Minecraft server subprocess."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Callable

from core.config import Config


class ServerManager:
    def __init__(self, config: Config, log_queue: Queue):
        self.config = config
        self.log_queue = log_queue          # (source, text) tuples
        self._proc: subprocess.Popen | None = None
        self._stdout_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.players: set[str] = set()
        self._status_callbacks: list[Callable[[str], None]] = []

    # ── public state ──────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def on_status_change(self, cb: Callable[[str], None]) -> None:
        self._status_callbacks.append(cb)

    def _emit_status(self, status: str) -> None:
        for cb in self._status_callbacks:
            try:
                cb(status)
            except Exception:
                pass

    # ── start / stop ──────────────────────────────────────────────────────────

    def start(self) -> tuple[bool, str]:
        if self.is_running:
            return False, "Server sudah berjalan."
        ok, msg = self.config.is_valid()
        if not ok:
            return False, msg

        argv = self.config.resolved_start_command()
        cwd = str(Path(self.config.get("server_dir")).resolve())
        self._log("SERVER", f"Starting: {' '.join(argv)}")

        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except FileNotFoundError as e:
            return False, f"Executable tidak ditemukan: {e}"
        except OSError as e:
            return False, f"Gagal start server: {e}"

        with self._lock:
            self._proc = proc
            self.players.clear()

        self._stdout_thread = threading.Thread(
            target=self._read_stdout, daemon=True
        )
        self._stdout_thread.start()
        self._emit_status("running")
        return True, "Server started."

    def stop(self, timeout: int | None = None) -> None:
        if not self.is_running:
            return
        t = timeout if timeout is not None else int(self.config.get("stop_timeout", 60))
        self.send_command("save-all")
        time.sleep(1)
        self.send_command(self.config.get("stop_command", "stop"))
        deadline = time.time() + t
        while time.time() < deadline:
            if not self.is_running:
                break
            time.sleep(0.5)
        self._force_kill()

    def stop_async(self, timeout: int | None = None, done_cb: Callable | None = None) -> None:
        def _run():
            self.stop(timeout)
            if done_cb:
                done_cb()
        threading.Thread(target=_run, daemon=True).start()

    def restart_async(self, done_cb: Callable | None = None) -> None:
        def _run():
            self.stop()
            time.sleep(2)
            self.start()
            if done_cb:
                done_cb()
        threading.Thread(target=_run, daemon=True).start()

    def _force_kill(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                time.sleep(2)
            if proc.poll() is None:
                proc.kill()
        except OSError:
            pass
        with self._lock:
            self._proc = None
            self.players.clear()
        self._emit_status("stopped")

    # ── command ───────────────────────────────────────────────────────────────

    def send_command(self, cmd: str) -> bool:
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            return False
        try:
            proc.stdin.write((cmd.strip() + "\n").encode("utf-8"))
            proc.stdin.flush()
            return True
        except OSError:
            return False

    # ── player helpers ────────────────────────────────────────────────────────

    def kick(self, name: str, reason: str = "Kicked by admin") -> None:
        self.send_command(f"kick {name} {reason}")

    def ban(self, name: str, reason: str = "Banned by admin") -> None:
        self.send_command(f"ban {name} {reason}")

    def unban(self, name: str) -> None:
        self.send_command(f"pardon {name}")

    def whitelist_add(self, name: str) -> None:
        self.send_command(f"whitelist add {name}")

    def whitelist_remove(self, name: str) -> None:
        self.send_command(f"whitelist remove {name}")

    # ── stdout reader ─────────────────────────────────────────────────────────

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            self._log("MC", line)
            self._parse_player_event(line)
        # process ended
        with self._lock:
            self._proc = None
            self.players.clear()
        self._emit_status("stopped")
        self._log("SERVER", "Server process ended.")

    def _parse_player_event(self, line: str) -> None:
        # Matches vanilla, Forge, Fabric:
        # [Server thread/INFO] [minecraft/...]: PlayerName joined the game
        import re
        m = re.search(r":\s+(\w+) (joined|left) the game", line)
        if m:
            name, event = m.group(1), m.group(2)
            if event == "joined":
                self.players.add(name)
            else:
                self.players.discard(name)

    def _log(self, source: str, text: str) -> None:
        self.log_queue.put((source, text))
