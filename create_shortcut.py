"""Create a Windows Desktop shortcut for MC Dashboard.
Called automatically on first run, or manually: python create_shortcut.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


APP_DIR  = Path(__file__).resolve().parent
MAIN_PY  = APP_DIR / "main.py"
ICON_PATH = APP_DIR / "icon.ico"
SHORTCUT_NAME = "MC Dashboard.lnk"


def _desktop() -> Path:
    """Return the current user's Desktop path."""
    import ctypes
    import ctypes.wintypes
    CSIDL_DESKTOP = 0
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOP, None, 0, buf)
    return Path(buf.value)


def _pythonw() -> Path:
    """Return pythonw.exe path (no console window). Falls back to python.exe."""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.is_file() else Path(sys.executable)


def shortcut_path() -> Path:
    return _desktop() / SHORTCUT_NAME


def shortcut_exists() -> bool:
    return shortcut_path().exists()


def create() -> tuple[bool, str]:
    target   = _pythonw()
    lnk_path = shortcut_path()
    icon_arg = str(ICON_PATH) if ICON_PATH.is_file() else str(target)

    # Build shortcut via PowerShell WScript.Shell COM object — no extra deps needed
    ps_script = f"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_path}')
$s.TargetPath      = '{target}'
$s.Arguments       = '"{MAIN_PY}"'
$s.WorkingDirectory= '{APP_DIR}'
$s.Description     = 'MC Dashboard — Minecraft Server Manager'
$s.IconLocation    = '{icon_arg},0'
$s.Save()
""".strip()

    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        return False, f"Gagal buat shortcut: {result.stderr.strip()}"
    return True, f"Shortcut dibuat di Desktop: {lnk_path.name}"


if __name__ == "__main__":
    ok, msg = create()
    print(msg)
    sys.exit(0 if ok else 1)
