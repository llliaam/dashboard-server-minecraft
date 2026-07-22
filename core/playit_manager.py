"""Manages the playit.gg CLI subprocess."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Callable


class PlayitManager:
    def __init__(self, log_queue: Queue):
        self.log_queue = log_queue
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._status_callbacks: list[Callable[[str], None]] = []

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

    def start(self, playit_path: str) -> tuple[bool, str]:
        if self.is_running:
            return False, "playit sudah berjalan."
        path = Path(playit_path)
        if not path.is_file():
            return False, f"playit.exe tidak ditemukan: {playit_path}"

        self._log("PLAYIT", f"Starting: {playit_path}")
        try:
            proc = subprocess.Popen(
                [str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as e:
            return False, f"Gagal start playit: {e}"

        with self._lock:
            self._proc = proc

        threading.Thread(target=self._read_stdout, daemon=True).start()
        self._emit_status("running")
        return True, "playit started."

    def stop(self) -> None:
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
        self._emit_status("stopped")
        self._log("PLAYIT", "playit stopped.")

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            self._log("PLAYIT", line)
        with self._lock:
            self._proc = None
        self._emit_status("stopped")
        self._log("PLAYIT", "playit process ended.")

    def _log(self, source: str, text: str) -> None:
        self.log_queue.put((source, text))
