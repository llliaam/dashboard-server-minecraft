"""World and datapack management."""
from __future__ import annotations

import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ── worlds ────────────────────────────────────────────────────────────────────

@dataclass
class WorldInfo:
    name: str           # folder name = level-name value
    path: Path
    active: bool
    size_mb: float
    has_nether: bool
    has_end: bool


def _folder_size_mb(p: Path) -> float:
    total = 0
    try:
        for f in p.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass
    return total / 1024 / 1024


def list_worlds(server_dir: str, active_name: str) -> list[WorldInfo]:
    d = Path(server_dir)
    worlds: list[WorldInfo] = []
    for child in sorted(d.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "level.dat").exists():
            continue
        worlds.append(WorldInfo(
            name=child.name,
            path=child,
            active=child.name == active_name,
            size_mb=_folder_size_mb(child),
            has_nether=(child / "DIM-1").exists() or (d / f"{child.name}_nether").exists(),
            has_end=(child / "DIM1").exists() or (d / f"{child.name}_the_end").exists(),
        ))
    return worlds


def backup_world(server_dir: str, world_name: str) -> tuple[bool, str]:
    src = Path(server_dir) / world_name
    if not src.is_dir():
        return False, f"Folder world '{world_name}' tidak ditemukan."

    backups_dir = Path(server_dir) / "backups"
    backups_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backups_dir / f"{world_name}_{ts}.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in src.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(src.parent))
        size_mb = zip_path.stat().st_size / 1024 / 1024
        return True, f"Backup selesai: {zip_path.name} ({size_mb:.1f} MB)"
    except Exception as e:
        return False, f"Backup gagal: {e}"


def delete_world(server_dir: str, world_name: str) -> tuple[bool, str]:
    base = Path(server_dir)
    targets = [
        base / world_name,
        base / f"{world_name}_nether",
        base / f"{world_name}_the_end",
    ]
    deleted = []
    for t in targets:
        if t.exists():
            shutil.rmtree(t)
            deleted.append(t.name)
    if deleted:
        return True, f"Dihapus: {', '.join(deleted)}"
    return False, f"Folder '{world_name}' tidak ditemukan."


# ── datapacks ─────────────────────────────────────────────────────────────────

@dataclass
class DatapackInfo:
    filename: str
    display_name: str
    enabled: bool
    is_zip: bool        # False = folder datapack
    size_mb: float


def _dp_dir(server_dir: str, world_name: str) -> Path:
    return Path(server_dir) / world_name / "datapacks"


def list_datapacks(server_dir: str, world_name: str) -> list[DatapackInfo]:
    d = _dp_dir(server_dir, world_name)
    if not d.is_dir():
        return []

    packs: list[DatapackInfo] = []
    for p in sorted(d.iterdir()):
        name = p.name
        if name.endswith(".zip"):
            is_zip, enabled, display = True, True, name.removesuffix(".zip")
        elif name.endswith(".zip.disabled"):
            is_zip, enabled, display = True, False, name.removesuffix(".zip.disabled")
        elif p.is_dir() and not name.startswith("."):
            is_zip, enabled, display = False, True, name
        else:
            continue

        size_mb = (p.stat().st_size / 1024 / 1024) if p.is_file() else _folder_size_mb(p)
        packs.append(DatapackInfo(
            filename=name,
            display_name=display,
            enabled=enabled,
            is_zip=is_zip,
            size_mb=size_mb,
        ))
    return packs


def toggle_datapack(server_dir: str, world_name: str, dp: DatapackInfo) -> DatapackInfo:
    d = _dp_dir(server_dir, world_name)
    if not dp.is_zip:
        raise ValueError("Folder datapack tidak bisa di-toggle via rename.")
    src = d / dp.filename
    if dp.enabled:
        dst = d / (dp.filename + ".disabled")
    else:
        dst = d / dp.filename.removesuffix(".disabled")
    src.rename(dst)
    return DatapackInfo(
        filename=dst.name,
        display_name=dp.display_name,
        enabled=not dp.enabled,
        is_zip=True,
        size_mb=dp.size_mb,
    )


def install_datapack(server_dir: str, world_name: str, src_path: str) -> tuple[bool, str]:
    src = Path(src_path)
    if not src.is_file():
        return False, f"File tidak ditemukan: {src_path}"
    if not src.name.endswith(".zip"):
        return False, "Hanya file .zip yang didukung."
    d = _dp_dir(server_dir, world_name)
    d.mkdir(parents=True, exist_ok=True)
    dst = d / src.name
    if dst.exists():
        return False, f"Datapack sudah ada: {src.name}"
    shutil.copy2(src, dst)
    return True, f"Datapack diinstall: {src.name}"


def delete_datapack(server_dir: str, world_name: str, dp: DatapackInfo) -> None:
    p = _dp_dir(server_dir, world_name) / dp.filename
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink(missing_ok=True)


def list_backups(server_dir: str) -> list[dict]:
    d = Path(server_dir) / "backups"
    if not d.is_dir():
        return []
    result = []
    for p in sorted(d.glob("*.zip"), reverse=True):
        result.append({
            "name": p.name,
            "size_mb": p.stat().st_size / 1024 / 1024,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return result
