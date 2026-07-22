"""Auto-shutdown scheduler. Runs in its own daemon thread."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable


class Scheduler:
    def __init__(
        self,
        config,
        on_warn: Callable[[int], None],
        on_shutdown: Callable[[], None],
    ):
        self.config = config
        self.on_warn = on_warn          # called with minutes remaining
        self.on_shutdown = on_shutdown  # called when it's time to stop
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._warned: set[int] = set()
        self._shutdown_triggered_date: str = ""

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                pass
            self._stop_event.wait(timeout=20)

    def _tick(self) -> None:
        cfg = self.config
        if not cfg.get("schedule_enabled", False):
            return

        sched_time_str: str = cfg.get("schedule_time", "23:00")
        sched_days: list[int] = cfg.get("schedule_days", list(range(7)))
        warn_minutes: list[int] = sorted(cfg.get("warn_minutes", [5, 1]), reverse=True)

        now = datetime.now()
        if now.weekday() not in sched_days:
            return

        try:
            h, m = map(int, sched_time_str.split(":"))
        except ValueError:
            return

        shutdown_hour = h
        shutdown_minute = m
        today_str = now.strftime("%Y-%m-%d")

        # minutes until shutdown today
        now_total = now.hour * 60 + now.minute
        sched_total = shutdown_hour * 60 + shutdown_minute
        diff_minutes = sched_total - now_total  # positive = future

        # trigger shutdown
        if diff_minutes <= 0 and self._shutdown_triggered_date != today_str:
            # allow a 1-minute window so we don't miss it
            if diff_minutes >= -1:
                self._shutdown_triggered_date = today_str
                self._warned.clear()
                self.on_shutdown()
            return

        # warnings
        for wm in warn_minutes:
            key = f"{today_str}:{wm}"
            if key in self._warned:
                continue
            # trigger when within [wm, wm-0.5) minutes
            if 0 < diff_minutes <= wm:
                self._warned.add(key)
                self.on_warn(wm)
