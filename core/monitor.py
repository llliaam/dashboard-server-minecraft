"""Polls CPU & RAM usage of the java server process."""
from __future__ import annotations

import threading
import time
from typing import Callable

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


class Monitor:
    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._callbacks: list[Callable[[dict], None]] = []

    def on_update(self, cb: Callable[[dict], None]) -> None:
        self._callbacks.append(cb)

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            data = self._collect()
            for cb in self._callbacks:
                try:
                    cb(data)
                except Exception:
                    pass
            self._stop_event.wait(timeout=self.interval)

    def _collect(self) -> dict:
        if not _PSUTIL:
            return {"cpu": 0.0, "ram_mb": 0.0, "sys_cpu": 0.0, "sys_ram_pct": 0.0}

        # find java process(es)
        java_cpu = 0.0
        java_ram = 0.0
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            try:
                if proc.info["name"] and "java" in proc.info["name"].lower():
                    java_cpu += proc.info["cpu_percent"] or 0.0
                    mi = proc.info["memory_info"]
                    if mi:
                        java_ram += mi.rss / 1024 / 1024
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        sys_cpu = psutil.cpu_percent()
        sys_ram = psutil.virtual_memory().percent

        return {
            "cpu": java_cpu,
            "ram_mb": java_ram,
            "sys_cpu": sys_cpu,
            "sys_ram_pct": sys_ram,
        }
