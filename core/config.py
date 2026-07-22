"""Persistent app configuration stored as JSON."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"

DEFAULTS: dict = {
    "server_dir": "",
    "start_command": "",
    "java_path": "java",
    "jar_name": "",
    "java_args": "-Xmx4G -Xms4G",
    "stop_command": "stop",
    "stop_timeout": 60,
    "playit_enabled": True,
    "playit_path": "",
    "playit_autostart": True,
    "schedule_enabled": False,
    "schedule_time": "23:00",
    "schedule_days": [0, 1, 2, 3, 4, 5, 6],
    "warn_minutes": [5, 1],
    "shutdown_pc": False,
    "theme": "dark",
    "console_buffer_lines": 2000,
}


class Config:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.data: dict = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for k, v in saved.items():
                    self.data[k] = v
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    def get(self, key: str, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def update(self, mapping: dict) -> None:
        self.data.update(mapping)

    def resolved_start_command(self) -> list[str]:
        """Return argv list for Popen."""
        cmd = self.get("start_command", "").strip()
        if cmd:
            import shlex
            return shlex.split(cmd)
        java = self.get("java_path", "java").strip() or "java"
        args_str = self.get("java_args", "").strip()
        jar = self.get("jar_name", "").strip()
        argv = [java]
        if args_str:
            import shlex
            argv += shlex.split(args_str)
        if jar:
            argv += ["-jar", jar, "nogui"]
        return argv

    def is_valid(self) -> tuple[bool, str]:
        d = self.get("server_dir", "")
        if not d or not Path(d).is_dir():
            return False, "Server directory belum di-set atau tidak ditemukan."
        if not self.get("start_command") and not self.get("jar_name"):
            return False, "Isi 'Start command' atau 'JAR name' di tab Settings."
        if self.get("playit_enabled"):
            p = self.get("playit_path", "")
            if p and not Path(p).is_file():
                return False, f"playit path tidak valid: {p}"
        return True, ""

    def auto_detect_from_runbat(self) -> dict:
        """Try to extract java args, jar name, and playit path from common locations."""
        found: dict = {}
        server_dir = Path(self.get("server_dir", ""))
        if not server_dir.is_dir():
            return found

        # playit.exe — cari di lokasi umum
        playit_candidates = [
            server_dir / "playit.exe",
            server_dir.parent / "playit.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "playit" / "playit.exe",
            Path(os.environ.get("APPDATA", "")) / "playit" / "playit.exe",
            Path("C:/playit/playit.exe"),
            Path("C:/tools/playit.exe"),
        ]
        for p in playit_candidates:
            if p.is_file():
                found["playit_path"] = str(p)
                break

        # user_jvm_args.txt (Forge 1.17+)
        jvm_file = server_dir / "user_jvm_args.txt"
        if jvm_file.exists():
            lines = jvm_file.read_text(encoding="utf-8", errors="replace").splitlines()
            args = " ".join(l.strip() for l in lines if l.strip() and not l.startswith("#"))
            if args:
                found["java_args"] = args

        # run.bat — look for java ... -jar <something>.jar
        for bat in ["run.bat", "start.bat"]:
            bat_path = server_dir / bat
            if not bat_path.exists():
                continue
            text = bat_path.read_text(encoding="utf-8", errors="replace")
            # find -jar <name>.jar
            m = re.search(r"-jar\s+\"?([^\s\"]+\.jar)\"?", text, re.IGNORECASE)
            if m:
                found["jar_name"] = m.group(1)
            # find -Xmx / -Xms block
            mx = re.findall(r"-X\w+\w+", text)
            if mx and "java_args" not in found:
                found["java_args"] = " ".join(mx)
            if found:
                break

        return found
