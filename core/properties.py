"""Read/write server.properties."""
from __future__ import annotations

from pathlib import Path


def load(server_dir: str) -> dict[str, str]:
    path = Path(server_dir) / "server.properties"
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def save(server_dir: str, props: dict[str, str]) -> None:
    path = Path(server_dir) / "server.properties"
    lines: list[str] = []

    # preserve existing comments / order if file exists
    existing_lines: list[str] = []
    existing_keys: dict[str, int] = {}
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(existing_lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                existing_keys[k] = i

    if existing_lines:
        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in props:
                    lines.append(f"{k}={props[k]}")
                    continue
            lines.append(line)
        # append new keys not in original
        for k, v in props.items():
            if k not in existing_keys:
                lines.append(f"{k}={v}")
    else:
        lines = [f"{k}={v}" for k, v in props.items()]

    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    import os
    os.replace(tmp, path)
