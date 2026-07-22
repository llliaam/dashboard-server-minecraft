"""Manages mods in the server's mods/ folder."""
from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModInfo:
    filename: str        # file name as-is on disk (may end in .disabled)
    jar_name: str        # actual .jar name (without .disabled)
    enabled: bool
    size_mb: float
    mod_id: str = ""
    display_name: str = ""
    version: str = ""
    description: str = ""

    @property
    def label(self) -> str:
        return self.display_name or self.mod_id or self.jar_name.removesuffix(".jar")


def _mods_dir(server_dir: str) -> Path:
    return Path(server_dir) / "mods"


def _read_fabric_meta(jar_path: Path) -> dict:
    try:
        with zipfile.ZipFile(jar_path, "r") as z:
            if "fabric.mod.json" in z.namelist():
                with z.open("fabric.mod.json") as f:
                    return json.loads(f.read().decode("utf-8", errors="replace"))
    except Exception:
        pass
    return {}


def list_mods(server_dir: str) -> list[ModInfo]:
    d = _mods_dir(server_dir)
    if not d.is_dir():
        return []

    mods: list[ModInfo] = []
    for p in sorted(d.iterdir()):
        name = p.name
        if name.endswith(".jar"):
            jar_name, enabled = name, True
        elif name.endswith(".jar.disabled"):
            jar_name, enabled = name.removesuffix(".disabled"), False
        else:
            continue

        size_mb = p.stat().st_size / 1024 / 1024
        meta = _read_fabric_meta(p)

        mods.append(ModInfo(
            filename=name,
            jar_name=jar_name,
            enabled=enabled,
            size_mb=size_mb,
            mod_id=meta.get("id", ""),
            display_name=meta.get("name", ""),
            version=str(meta.get("version", "")),
            description=meta.get("description", ""),
        ))

    return mods


def toggle_mod(server_dir: str, mod: ModInfo) -> ModInfo:
    """Enable or disable a mod by renaming the file. Returns updated ModInfo."""
    d = _mods_dir(server_dir)
    src = d / mod.filename
    if mod.enabled:
        dst = d / (mod.jar_name + ".disabled")
    else:
        dst = d / mod.jar_name
    src.rename(dst)
    return ModInfo(
        filename=dst.name,
        jar_name=mod.jar_name,
        enabled=not mod.enabled,
        size_mb=mod.size_mb,
        mod_id=mod.mod_id,
        display_name=mod.display_name,
        version=mod.version,
        description=mod.description,
    )


def delete_mod(server_dir: str, mod: ModInfo) -> None:
    p = _mods_dir(server_dir) / mod.filename
    p.unlink(missing_ok=True)


def install_mod(server_dir: str, src_path: str) -> tuple[bool, str]:
    """Copy a .jar file into the mods folder."""
    src = Path(src_path)
    if not src.is_file():
        return False, f"File tidak ditemukan: {src_path}"
    if not src.name.endswith(".jar"):
        return False, "Hanya file .jar yang bisa diinstall."
    d = _mods_dir(server_dir)
    d.mkdir(exist_ok=True)
    dst = d / src.name
    if dst.exists():
        return False, f"Mod sudah ada: {src.name}"
    shutil.copy2(src, dst)
    return True, f"Mod diinstall: {src.name}"
