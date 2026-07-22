"""Main application window with all tabs."""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox

import customtkinter as ctk

# Add project root to path so `core` is importable when running from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from core.mod_manager import ModInfo, delete_mod, install_mod, list_mods, toggle_mod
from core.monitor import Monitor
from core.world_manager import (
    DatapackInfo, WorldInfo,
    backup_world, delete_datapack, delete_world,
    install_datapack, list_backups, list_datapacks,
    list_worlds, toggle_datapack,
)
from core.playit_manager import PlayitManager
from core.properties import load as props_load
from core.properties import save as props_save
from core.scheduler import Scheduler
from core.server_manager import ServerManager

# ── color tokens ──────────────────────────────────────────────────────────────
C_GREEN  = "#4caf50"
C_RED    = "#f44336"
C_ORANGE = "#ff9800"
C_BLUE   = "#2196f3"
C_GRAY   = "#9e9e9e"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MC Dashboard")
        self.geometry("1100x720")
        self.minsize(900, 600)

        self.config_obj = Config()
        ctk.set_appearance_mode(self.config_obj.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self.log_queue: Queue = Queue()
        self.server = ServerManager(self.config_obj, self.log_queue)
        self.playit = PlayitManager(self.log_queue)
        self.monitor = Monitor(interval=2.0)
        self.scheduler = Scheduler(
            self.config_obj,
            on_warn=self._on_sched_warn,
            on_shutdown=self._on_sched_shutdown,
        )

        self.server.on_status_change(self._on_server_status)
        self.playit.on_status_change(self._on_playit_status)
        self.monitor.on_update(self._on_monitor_update)

        self._build_layout()
        self.monitor.start()
        self.scheduler.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_log_queue)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # top bar
        top = ctk.CTkFrame(self, height=52, fg_color=("gray90", "gray15"))
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        self._build_topbar(top)

        # tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        for name in ("Console", "Players", "Mods", "Worlds", "Scheduler", "Properties", "Settings"):
            self.tabs.add(name)

        self._build_console_tab(self.tabs.tab("Console"))
        self._build_players_tab(self.tabs.tab("Players"))
        self._build_mods_tab(self.tabs.tab("Mods"))
        self._build_worlds_tab(self.tabs.tab("Worlds"))
        self._build_scheduler_tab(self.tabs.tab("Scheduler"))
        self._build_properties_tab(self.tabs.tab("Properties"))
        self._build_settings_tab(self.tabs.tab("Settings"))

    # ── top bar ───────────────────────────────────────────────────────────────

    def _build_topbar(self, parent) -> None:
        parent.columnconfigure(5, weight=1)

        self.lbl_title = ctk.CTkLabel(parent, text="⛏ MC Dashboard", font=("", 16, "bold"))
        self.lbl_title.grid(row=0, column=0, padx=14, pady=10)

        self.btn_start = ctk.CTkButton(parent, text="▶ Start", width=90,
                                       fg_color=C_GREEN, hover_color="#388e3c",
                                       command=self._cmd_start)
        self.btn_start.grid(row=0, column=1, padx=4)

        self.btn_stop = ctk.CTkButton(parent, text="■ Stop", width=90,
                                      fg_color=C_RED, hover_color="#c62828",
                                      state="disabled", command=self._cmd_stop)
        self.btn_stop.grid(row=0, column=2, padx=4)

        self.btn_restart = ctk.CTkButton(parent, text="↺ Restart", width=90,
                                         fg_color=C_ORANGE, hover_color="#e65100",
                                         state="disabled", command=self._cmd_restart)
        self.btn_restart.grid(row=0, column=3, padx=4)

        self.lbl_server_status = ctk.CTkLabel(parent, text="● Offline",
                                              text_color=C_GRAY, font=("", 12))
        self.lbl_server_status.grid(row=0, column=4, padx=10)

        # resource meters
        self.lbl_cpu = ctk.CTkLabel(parent, text="CPU: --", font=("", 11))
        self.lbl_cpu.grid(row=0, column=6, padx=6)
        self.lbl_ram = ctk.CTkLabel(parent, text="RAM: --", font=("", 11))
        self.lbl_ram.grid(row=0, column=7, padx=6)

        self.lbl_playit = ctk.CTkLabel(parent, text="playit: ●", text_color=C_GRAY, font=("", 11))
        self.lbl_playit.grid(row=0, column=8, padx=10)

    # ── console tab ───────────────────────────────────────────────────────────

    def _build_console_tab(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.console_box = ctk.CTkTextbox(parent, wrap="word", font=("Consolas", 12),
                                          state="disabled")
        self.console_box.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        cmd_frame = ctk.CTkFrame(parent, fg_color="transparent")
        cmd_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
        cmd_frame.columnconfigure(0, weight=1)

        self.cmd_entry = ctk.CTkEntry(cmd_frame, placeholder_text="Ketik command → Enter")
        self.cmd_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.cmd_entry.bind("<Return>", self._send_command)

        self.btn_send = ctk.CTkButton(cmd_frame, text="Kirim", width=70,
                                      command=self._send_command)
        self.btn_send.grid(row=0, column=1)

        self.btn_clear = ctk.CTkButton(cmd_frame, text="Clear", width=60,
                                       fg_color="gray40", hover_color="gray30",
                                       command=self._clear_console)
        self.btn_clear.grid(row=0, column=2, padx=(4, 0))

    # ── players tab ───────────────────────────────────────────────────────────

    def _build_players_tab(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        info_bar = ctk.CTkFrame(parent, fg_color="transparent")
        info_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.lbl_player_count = ctk.CTkLabel(info_bar, text="Players online: 0", font=("", 13, "bold"))
        self.lbl_player_count.pack(side="left", padx=6)
        ctk.CTkButton(info_bar, text="↻ Refresh", width=80, command=self._refresh_players).pack(side="left", padx=4)

        self.player_frame = ctk.CTkScrollableFrame(parent)
        self.player_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.player_frame.columnconfigure(0, weight=1)

        # ban / whitelist section (offline operations)
        sep = ctk.CTkFrame(parent, height=2, fg_color="gray40")
        sep.grid(row=2, column=0, sticky="ew", padx=10, pady=4)

        offline_frame = ctk.CTkFrame(parent, fg_color="transparent")
        offline_frame.grid(row=3, column=0, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkLabel(offline_frame, text="Offline actions — username:").pack(side="left", padx=6)
        self.offline_entry = ctk.CTkEntry(offline_frame, width=160, placeholder_text="playername")
        self.offline_entry.pack(side="left", padx=4)
        for txt, cmd in [("Ban", self._ban_offline), ("Unban", self._unban_offline),
                         ("WL Add", self._wl_add_offline), ("WL Remove", self._wl_remove_offline)]:
            ctk.CTkButton(offline_frame, text=txt, width=75, command=cmd).pack(side="left", padx=3)

    def _refresh_players(self) -> None:
        # rebuild player rows
        for w in self.player_frame.winfo_children():
            w.destroy()
        players = sorted(self.server.players)
        self.lbl_player_count.configure(text=f"Players online: {len(players)}")
        for i, name in enumerate(players):
            row = ctk.CTkFrame(self.player_frame, fg_color=("gray85", "gray20"))
            row.pack(fill="x", padx=4, pady=2)
            row.columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=f"  {name}", anchor="w").grid(row=0, column=0, sticky="w", padx=8)
            ctk.CTkButton(row, text="Kick", width=55, fg_color=C_ORANGE, hover_color="#e65100",
                          command=lambda n=name: self._kick_player(n)).grid(row=0, column=1, padx=4, pady=4)
            ctk.CTkButton(row, text="Ban", width=55, fg_color=C_RED, hover_color="#c62828",
                          command=lambda n=name: self._ban_player(n)).grid(row=0, column=2, padx=(0, 8), pady=4)

    def _kick_player(self, name: str) -> None:
        self.server.kick(name)
        self._log_ui(f"[UI] Kicked {name}")

    def _ban_player(self, name: str) -> None:
        if messagebox.askyesno("Ban", f"Ban {name}?"):
            self.server.ban(name)
            self._log_ui(f"[UI] Banned {name}")

    def _ban_offline(self) -> None:
        n = self.offline_entry.get().strip()
        if n:
            self.server.ban(n)
            self._log_ui(f"[UI] Ban sent: {n}")

    def _unban_offline(self) -> None:
        n = self.offline_entry.get().strip()
        if n:
            self.server.unban(n)
            self._log_ui(f"[UI] Unban sent: {n}")

    def _wl_add_offline(self) -> None:
        n = self.offline_entry.get().strip()
        if n:
            self.server.whitelist_add(n)
            self._log_ui(f"[UI] Whitelist add: {n}")

    def _wl_remove_offline(self) -> None:
        n = self.offline_entry.get().strip()
        if n:
            self.server.whitelist_remove(n)
            self._log_ui(f"[UI] Whitelist remove: {n}")

    # ── mods tab ──────────────────────────────────────────────────────────────

    def _build_mods_tab(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # toolbar
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(bar, text="↻ Refresh", width=80, command=self._mods_refresh).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="+ Install Mod", width=110, fg_color=C_BLUE,
                      command=self._mods_install).pack(side="left", padx=4)
        self.lbl_mod_count = ctk.CTkLabel(bar, text="", text_color=C_GRAY)
        self.lbl_mod_count.pack(side="left", padx=8)
        self.lbl_mod_warning = ctk.CTkLabel(bar, text="⚠ Restart server agar perubahan berlaku",
                                            text_color=C_ORANGE)
        self.lbl_mod_warning.pack(side="right", padx=8)
        self.lbl_mod_warning.pack_forget()  # hidden until a change is made

        # search bar
        search_frame = ctk.CTkFrame(parent, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 2))
        search_frame.columnconfigure(1, weight=1)
        ctk.CTkLabel(search_frame, text="Cari:", width=40).grid(row=0, column=0, padx=(4, 4))
        self._mod_search_var = ctk.StringVar()
        self._mod_search_var.trace_add("write", lambda *_: self._mods_apply_filter())
        ctk.CTkEntry(search_frame, textvariable=self._mod_search_var,
                     placeholder_text="nama mod...").grid(row=0, column=1, sticky="ew", padx=(0, 4))

        # scrollable list
        self._mods_scroll = ctk.CTkScrollableFrame(parent)
        self._mods_scroll.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._mods_scroll.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        self._mod_rows: list[dict] = []  # cache of rendered rows
        self._mods_data: list[ModInfo] = []

        # detail panel at bottom
        self._mod_detail = ctk.CTkLabel(parent, text="", text_color=C_GRAY,
                                        font=("", 11), anchor="w", wraplength=700)
        self._mod_detail.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 6))

        self._mods_refresh()

    def _mods_refresh(self) -> None:
        d = self.config_obj.get("server_dir", "")
        if not d:
            self.lbl_mod_count.configure(text="Set server directory di Settings dulu.")
            return
        self._mods_data = list_mods(d)
        self._mods_apply_filter()

    def _mods_apply_filter(self) -> None:
        query = self._mod_search_var.get().lower().strip()
        visible = [m for m in self._mods_data
                   if not query or query in m.label.lower() or query in m.mod_id.lower()]
        self._mods_render(visible)
        enabled = sum(1 for m in self._mods_data if m.enabled)
        total = len(self._mods_data)
        self.lbl_mod_count.configure(text=f"{total} mod  |  {enabled} aktif")

    def _mods_render(self, mods: list[ModInfo]) -> None:
        for w in self._mods_scroll.winfo_children():
            w.destroy()
        self._mod_rows.clear()

        for i, mod in enumerate(mods):
            bg = ("gray85", "gray20") if mod.enabled else ("gray80", "gray17")
            row = ctk.CTkFrame(self._mods_scroll, fg_color=bg)
            row.pack(fill="x", padx=4, pady=2)
            row.columnconfigure(1, weight=1)

            # toggle switch
            var = ctk.BooleanVar(value=mod.enabled)
            sw = ctk.CTkSwitch(row, text="", variable=var, width=48,
                               command=lambda m=mod, v=var: self._mods_toggle(m, v))
            sw.grid(row=0, column=0, padx=(8, 4), pady=6)

            # name + version
            lbl_name = ctk.CTkLabel(row, text=f"{mod.label}  v{mod.version}" if mod.version else mod.label,
                                    anchor="w", font=("", 12, "bold" if mod.enabled else "normal"))
            lbl_name.grid(row=0, column=1, sticky="w", padx=4)
            lbl_name.bind("<Button-1>", lambda e, m=mod: self._mods_show_detail(m))

            # size
            ctk.CTkLabel(row, text=f"{mod.size_mb:.1f} MB",
                         text_color=C_GRAY, font=("", 10)).grid(row=0, column=2, padx=8)

            # delete button
            ctk.CTkButton(row, text="🗑", width=34, fg_color="transparent",
                          hover_color=C_RED, text_color=("gray20", "gray80"),
                          command=lambda m=mod: self._mods_delete(m)).grid(row=0, column=3, padx=(0, 6))

            self._mod_rows.append({"mod": mod, "var": var, "row": row})

    def _mods_toggle(self, mod: ModInfo, var: ctk.BooleanVar) -> None:
        d = self.config_obj.get("server_dir", "")
        try:
            updated = toggle_mod(d, mod)
            # update in-place in _mods_data
            for i, m in enumerate(self._mods_data):
                if m.filename == mod.filename:
                    self._mods_data[i] = updated
                    break
            self.lbl_mod_warning.pack(side="right", padx=8)
            self._mods_apply_filter()
        except OSError as e:
            messagebox.showerror("Toggle Mod", f"Gagal: {e}")
            var.set(mod.enabled)  # revert switch

    def _mods_delete(self, mod: ModInfo) -> None:
        if not messagebox.askyesno("Hapus Mod", f"Hapus '{mod.label}'?\nIni permanen."):
            return
        d = self.config_obj.get("server_dir", "")
        try:
            delete_mod(d, mod)
            self._mods_data = [m for m in self._mods_data if m.filename != mod.filename]
            self.lbl_mod_warning.pack(side="right", padx=8)
            self._mods_apply_filter()
            self._mod_detail.configure(text="")
        except OSError as e:
            messagebox.showerror("Hapus Mod", f"Gagal: {e}")

    def _mods_install(self) -> None:
        d = self.config_obj.get("server_dir", "")
        if not d:
            messagebox.showwarning("Install Mod", "Set server directory di Settings dulu.")
            return
        paths = filedialog.askopenfilenames(
            title="Pilih file mod (.jar)",
            filetypes=[("JAR files", "*.jar"), ("All files", "*.*")],
        )
        if not paths:
            return
        results = []
        for p in paths:
            ok, msg = install_mod(d, p)
            results.append(msg)
        messagebox.showinfo("Install Mod", "\n".join(results))
        self.lbl_mod_warning.pack(side="right", padx=8)
        self._mods_refresh()

    def _mods_show_detail(self, mod: ModInfo) -> None:
        parts = []
        if mod.mod_id:
            parts.append(f"ID: {mod.mod_id}")
        if mod.description:
            parts.append(f"Desc: {mod.description}")
        parts.append(f"File: {mod.filename}")
        self._mod_detail.configure(text="  |  ".join(parts))

    # ── worlds tab ────────────────────────────────────────────────────────────

    def _build_worlds_tab(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)

        # ── left: world list ──────────────────────────────────────────────────
        left = ctk.CTkFrame(parent)
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(4, 2), pady=4)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        lbar = ctk.CTkFrame(left, fg_color="transparent")
        lbar.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ctk.CTkLabel(lbar, text="Worlds", font=("", 13, "bold")).pack(side="left", padx=4)
        ctk.CTkButton(lbar, text="↻", width=32, command=self._worlds_refresh).pack(side="left", padx=2)

        self._world_scroll = ctk.CTkScrollableFrame(left)
        self._world_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._world_scroll.columnconfigure(0, weight=1)

        self._worlds_data: list[WorldInfo] = []
        self._selected_world: WorldInfo | None = None

        # ── right: detail + datapacks + backups ──────────────────────────────
        right = ctk.CTkFrame(parent)
        right.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(2, 4), pady=4)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        self._lbl_world_title = ctk.CTkLabel(right, text="Pilih world di kiri",
                                             font=("", 13, "bold"))
        self._lbl_world_title.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        self._lbl_world_info = ctk.CTkLabel(right, text="", text_color=C_GRAY,
                                            font=("", 11), anchor="w")
        self._lbl_world_info.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

        # world action buttons
        wact = ctk.CTkFrame(right, fg_color="transparent")
        wact.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 6))
        self._btn_world_backup = ctk.CTkButton(wact, text="💾 Backup", width=100,
                                               fg_color=C_BLUE, state="disabled",
                                               command=self._world_backup)
        self._btn_world_backup.pack(side="left", padx=4)
        self._btn_world_activate = ctk.CTkButton(wact, text="✓ Set Aktif", width=100,
                                                  fg_color=C_GREEN, hover_color="#388e3c",
                                                  state="disabled",
                                                  command=self._world_set_active)
        self._btn_world_activate.pack(side="left", padx=4)
        self._btn_world_delete = ctk.CTkButton(wact, text="🗑 Hapus", width=90,
                                               fg_color=C_RED, hover_color="#c62828",
                                               state="disabled",
                                               command=self._world_delete)
        self._btn_world_delete.pack(side="left", padx=4)

        # datapacks sub-section
        ctk.CTkLabel(right, text="Datapacks", font=("", 12, "bold")).grid(
            row=3, column=0, sticky="w", padx=10, pady=(4, 0))

        dpbar = ctk.CTkFrame(right, fg_color="transparent")
        dpbar.grid(row=4, column=0, sticky="ew", padx=6, pady=(2, 2))
        ctk.CTkButton(dpbar, text="↻ Refresh", width=80,
                      command=self._dp_refresh).pack(side="left", padx=4)
        ctk.CTkButton(dpbar, text="+ Install .zip", width=100, fg_color=C_BLUE,
                      command=self._dp_install).pack(side="left", padx=4)
        ctk.CTkButton(dpbar, text="⟳ /reload", width=90, fg_color=C_ORANGE,
                      command=self._dp_reload).pack(side="left", padx=4)

        self._dp_scroll = ctk.CTkScrollableFrame(right, height=160)
        self._dp_scroll.grid(row=5, column=0, sticky="ew", padx=4, pady=(0, 4))
        self._dp_scroll.columnconfigure(0, weight=1)
        right.rowconfigure(5, weight=1)

        # backups sub-section
        ctk.CTkLabel(right, text="Backups", font=("", 12, "bold")).grid(
            row=6, column=0, sticky="w", padx=10, pady=(4, 0))
        self._backup_scroll = ctk.CTkScrollableFrame(right, height=120)
        self._backup_scroll.grid(row=7, column=0, sticky="ew", padx=4, pady=(2, 6))
        self._backup_scroll.columnconfigure(0, weight=1)

        self._worlds_refresh()

    # ── world helpers ─────────────────────────────────────────────────────────

    def _active_world_name(self) -> str:
        from core.properties import load as _pload
        d = self.config_obj.get("server_dir", "")
        if not d:
            return ""
        props = _pload(d)
        return props.get("level-name", "world")

    def _worlds_refresh(self) -> None:
        d = self.config_obj.get("server_dir", "")
        if not d:
            return
        active = self._active_world_name()
        self._worlds_data = list_worlds(d, active)
        self._render_world_list()
        self._backups_refresh()

    def _render_world_list(self) -> None:
        for w in self._world_scroll.winfo_children():
            w.destroy()
        for world in self._worlds_data:
            bg = ("gray78", "gray25") if world.active else ("gray85", "gray20")
            row = ctk.CTkFrame(self._world_scroll, fg_color=bg, cursor="hand2")
            row.pack(fill="x", padx=4, pady=2)
            row.columnconfigure(0, weight=1)
            label = f"{'★ ' if world.active else '  '}{world.name}"
            ctk.CTkLabel(row, text=label, anchor="w",
                         font=("", 12, "bold" if world.active else "normal")).grid(
                row=0, column=0, sticky="w", padx=8, pady=4)
            ctk.CTkLabel(row, text=f"{world.size_mb:.1f} MB",
                         text_color=C_GRAY, font=("", 10)).grid(row=0, column=1, padx=8)
            row.bind("<Button-1>", lambda e, ww=world: self._world_select(ww))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, ww=world: self._world_select(ww))

    def _world_select(self, world: WorldInfo) -> None:
        self._selected_world = world
        self._lbl_world_title.configure(text=f"{'[AKTIF] ' if world.active else ''}{world.name}")
        dims = []
        if world.has_nether:
            dims.append("Nether")
        if world.has_end:
            dims.append("The End")
        dim_str = ", ".join(dims) if dims else "Overworld only"
        self._lbl_world_info.configure(
            text=f"Ukuran: {world.size_mb:.1f} MB  |  Dimensi: {dim_str}")
        self._btn_world_backup.configure(state="normal")
        self._btn_world_delete.configure(
            state="disabled" if world.active else "normal")
        self._btn_world_activate.configure(
            state="disabled" if world.active else "normal")
        self._dp_refresh()

    def _world_backup(self) -> None:
        if not self._selected_world:
            return
        d = self.config_obj.get("server_dir", "")
        if self.server.is_running:
            self.server.send_command("save-all")
            import time; time.sleep(1)
        ok, msg = backup_world(d, self._selected_world.name)
        messagebox.showinfo("Backup World", msg)
        self._backups_refresh()

    def _world_set_active(self) -> None:
        if not self._selected_world:
            return
        if self.server.is_running:
            messagebox.showwarning("Set Aktif", "Stop server dulu sebelum mengganti world aktif.")
            return
        from core.properties import load as _pload, save as _psave
        d = self.config_obj.get("server_dir", "")
        props = _pload(d)
        props["level-name"] = self._selected_world.name
        _psave(d, props)
        messagebox.showinfo("Set Aktif", f"World aktif diubah ke '{self._selected_world.name}'.\nStart server untuk berlaku.")
        self._worlds_refresh()

    def _world_delete(self) -> None:
        if not self._selected_world:
            return
        if self._selected_world.active:
            messagebox.showerror("Hapus World", "Tidak bisa menghapus world yang sedang aktif.")
            return
        if self.server.is_running:
            messagebox.showwarning("Hapus World", "Stop server dulu sebelum menghapus world.")
            return
        name = self._selected_world.name
        if not messagebox.askyesno("Hapus World",
                                   f"Hapus world '{name}' beserta Nether & The End-nya?\n"
                                   f"⚠ Ini PERMANEN dan tidak bisa dibatalkan!"):
            return
        d = self.config_obj.get("server_dir", "")
        ok, msg = delete_world(d, name)
        messagebox.showinfo("Hapus World", msg)
        self._selected_world = None
        self._lbl_world_title.configure(text="Pilih world di kiri")
        self._lbl_world_info.configure(text="")
        for btn in (self._btn_world_backup, self._btn_world_activate, self._btn_world_delete):
            btn.configure(state="disabled")
        self._worlds_refresh()

    # ── datapack helpers ──────────────────────────────────────────────────────

    def _dp_refresh(self) -> None:
        for w in self._dp_scroll.winfo_children():
            w.destroy()
        if not self._selected_world:
            return
        d = self.config_obj.get("server_dir", "")
        packs = list_datapacks(d, self._selected_world.name)
        if not packs:
            ctk.CTkLabel(self._dp_scroll, text="Tidak ada datapack.",
                         text_color=C_GRAY).pack(anchor="w", padx=8)
            return
        for dp in packs:
            bg = ("gray85", "gray20") if dp.enabled else ("gray80", "gray17")
            row = ctk.CTkFrame(self._dp_scroll, fg_color=bg)
            row.pack(fill="x", padx=2, pady=1)
            row.columnconfigure(1, weight=1)

            if dp.is_zip:
                var = ctk.BooleanVar(value=dp.enabled)
                sw = ctk.CTkSwitch(row, text="", variable=var, width=48,
                                   command=lambda p=dp, v=var: self._dp_toggle(p, v))
                sw.grid(row=0, column=0, padx=(6, 2), pady=4)
            else:
                ctk.CTkLabel(row, text="📁", width=48).grid(row=0, column=0, padx=6)

            ctk.CTkLabel(row, text=dp.display_name, anchor="w").grid(
                row=0, column=1, sticky="w", padx=4)
            ctk.CTkLabel(row, text=f"{dp.size_mb:.2f} MB",
                         text_color=C_GRAY, font=("", 10)).grid(row=0, column=2, padx=6)
            ctk.CTkButton(row, text="🗑", width=34, fg_color="transparent",
                          hover_color=C_RED, text_color=("gray20", "gray80"),
                          command=lambda p=dp: self._dp_delete(p)).grid(
                row=0, column=3, padx=(0, 4))

    def _dp_toggle(self, dp: DatapackInfo, var: ctk.BooleanVar) -> None:
        d = self.config_obj.get("server_dir", "")
        try:
            toggle_datapack(d, self._selected_world.name, dp)
            self._dp_refresh()
        except Exception as e:
            messagebox.showerror("Toggle Datapack", str(e))
            var.set(dp.enabled)

    def _dp_install(self) -> None:
        if not self._selected_world:
            messagebox.showwarning("Install Datapack", "Pilih world dulu.")
            return
        paths = filedialog.askopenfilenames(
            title="Pilih datapack (.zip)",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        )
        if not paths:
            return
        d = self.config_obj.get("server_dir", "")
        results = []
        for p in paths:
            ok, msg = install_datapack(d, self._selected_world.name, p)
            results.append(msg)
        messagebox.showinfo("Install Datapack", "\n".join(results))
        self._dp_refresh()

    def _dp_delete(self, dp: DatapackInfo) -> None:
        if not messagebox.askyesno("Hapus Datapack", f"Hapus '{dp.display_name}'?"):
            return
        d = self.config_obj.get("server_dir", "")
        try:
            delete_datapack(d, self._selected_world.name, dp)
            self._dp_refresh()
        except Exception as e:
            messagebox.showerror("Hapus Datapack", str(e))

    def _dp_reload(self) -> None:
        if not self.server.is_running:
            messagebox.showwarning("/reload", "Server tidak berjalan.")
            return
        self.server.send_command("reload")
        self._log_ui("[UI] /reload dikirim ke server.")

    # ── backup list ───────────────────────────────────────────────────────────

    def _backups_refresh(self) -> None:
        for w in self._backup_scroll.winfo_children():
            w.destroy()
        d = self.config_obj.get("server_dir", "")
        if not d:
            return
        backups = list_backups(d)
        if not backups:
            ctk.CTkLabel(self._backup_scroll, text="Belum ada backup.",
                         text_color=C_GRAY).pack(anchor="w", padx=8)
            return
        for b in backups:
            row = ctk.CTkFrame(self._backup_scroll, fg_color=("gray85", "gray20"))
            row.pack(fill="x", padx=2, pady=1)
            row.columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=b["name"], anchor="w", font=("Consolas", 11)).grid(
                row=0, column=0, sticky="w", padx=8, pady=3)
            ctk.CTkLabel(row, text=f"{b['size_mb']:.1f} MB  {b['mtime']}",
                         text_color=C_GRAY, font=("", 10)).grid(row=0, column=1, padx=8)

    # ── scheduler tab ─────────────────────────────────────────────────────────

    def _build_scheduler_tab(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        pad = {"padx": 16, "pady": 6}

        ctk.CTkLabel(parent, text="Auto-Shutdown Scheduler", font=("", 15, "bold")).pack(anchor="w", **pad)

        en_frame = ctk.CTkFrame(parent, fg_color="transparent")
        en_frame.pack(fill="x", **pad)
        self.sched_enabled_var = ctk.BooleanVar(value=self.config_obj.get("schedule_enabled", False))
        ctk.CTkSwitch(en_frame, text="Aktifkan auto-shutdown",
                      variable=self.sched_enabled_var).pack(side="left")

        time_frame = ctk.CTkFrame(parent, fg_color="transparent")
        time_frame.pack(fill="x", **pad)
        ctk.CTkLabel(time_frame, text="Jam shutdown (HH:MM):", width=180, anchor="w").pack(side="left")
        self.sched_time_var = ctk.StringVar(value=self.config_obj.get("schedule_time", "23:00"))
        ctk.CTkEntry(time_frame, textvariable=self.sched_time_var, width=80).pack(side="left")

        ctk.CTkLabel(parent, text="Hari aktif:", anchor="w").pack(anchor="w", padx=16, pady=(8, 0))
        days_frame = ctk.CTkFrame(parent, fg_color="transparent")
        days_frame.pack(fill="x", padx=16, pady=(2, 6))
        day_names = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
        sched_days = self.config_obj.get("schedule_days", list(range(7)))
        self.day_vars: list[ctk.BooleanVar] = []
        for i, dname in enumerate(day_names):
            v = ctk.BooleanVar(value=i in sched_days)
            self.day_vars.append(v)
            ctk.CTkCheckBox(days_frame, text=dname, variable=v, width=60).grid(row=0, column=i, padx=4)

        warn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        warn_frame.pack(fill="x", **pad)
        ctk.CTkLabel(warn_frame, text="Warning in-game (menit, pisahkan koma):", width=300, anchor="w").pack(side="left")
        wm = self.config_obj.get("warn_minutes", [5, 1])
        self.warn_var = ctk.StringVar(value=", ".join(str(x) for x in wm))
        ctk.CTkEntry(warn_frame, textvariable=self.warn_var, width=120).pack(side="left")

        ctk.CTkButton(parent, text="Simpan Jadwal", command=self._save_scheduler).pack(anchor="w", **pad)

        # status label
        self.lbl_sched_status = ctk.CTkLabel(parent, text="", text_color=C_BLUE)
        self.lbl_sched_status.pack(anchor="w", **pad)

        # next trigger display
        self.lbl_next_shutdown = ctk.CTkLabel(parent, text="", font=("", 12))
        self.lbl_next_shutdown.pack(anchor="w", **pad)
        self.after(1000, self._update_next_shutdown_label)

    def _save_scheduler(self) -> None:
        days = [i for i, v in enumerate(self.day_vars) if v.get()]
        try:
            warn = [int(x.strip()) for x in self.warn_var.get().split(",") if x.strip()]
        except ValueError:
            warn = [5, 1]
        self.config_obj.update({
            "schedule_enabled": self.sched_enabled_var.get(),
            "schedule_time": self.sched_time_var.get().strip(),
            "schedule_days": days,
            "warn_minutes": sorted(warn, reverse=True),
        })
        self.config_obj.save()
        self.lbl_sched_status.configure(text="✓ Jadwal disimpan.", text_color=C_GREEN)
        self.after(3000, lambda: self.lbl_sched_status.configure(text=""))

    def _update_next_shutdown_label(self) -> None:
        if self.config_obj.get("schedule_enabled", False):
            t = self.config_obj.get("schedule_time", "--:--")
            days = self.config_obj.get("schedule_days", [])
            day_names = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
            day_str = ", ".join(day_names[d] for d in days) if days else "—"
            self.lbl_next_shutdown.configure(
                text=f"Shutdown aktif: pukul {t}  |  Hari: {day_str}")
        else:
            self.lbl_next_shutdown.configure(text="Scheduler dinonaktifkan.")
        self.after(10000, self._update_next_shutdown_label)

    # ── properties tab ────────────────────────────────────────────────────────

    def _build_properties_tab(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        btn_bar = ctk.CTkFrame(parent, fg_color="transparent")
        btn_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(btn_bar, text="↻ Muat", width=80, command=self._load_properties).pack(side="left", padx=4)
        ctk.CTkButton(btn_bar, text="💾 Simpan", width=90, command=self._save_properties).pack(side="left", padx=4)
        ctk.CTkLabel(btn_bar, text="  (Butuh restart server agar berlaku)", text_color=C_GRAY).pack(side="left")

        self.props_scroll = ctk.CTkScrollableFrame(parent)
        self.props_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.props_scroll.columnconfigure(1, weight=1)
        self._props_widgets: dict[str, ctk.CTkEntry] = {}

    def _load_properties(self) -> None:
        d = self.config_obj.get("server_dir", "")
        if not d:
            messagebox.showwarning("Properties", "Set server directory di Settings dulu.")
            return
        props = props_load(d)
        for w in self.props_scroll.winfo_children():
            w.destroy()
        self._props_widgets.clear()
        for i, (k, v) in enumerate(sorted(props.items())):
            ctk.CTkLabel(self.props_scroll, text=k, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(8, 12), pady=2)
            ent = ctk.CTkEntry(self.props_scroll)
            ent.insert(0, v)
            ent.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=2)
            self._props_widgets[k] = ent

    def _save_properties(self) -> None:
        d = self.config_obj.get("server_dir", "")
        if not d or not self._props_widgets:
            return
        props = {k: ent.get() for k, ent in self._props_widgets.items()}
        props_save(d, props)
        messagebox.showinfo("Properties", "server.properties disimpan.\nRestart server agar berlaku.")

    # ── settings tab ──────────────────────────────────────────────────────────

    def _build_settings_tab(self, parent) -> None:
        parent.columnconfigure(1, weight=1)
        cfg = self.config_obj
        self._svar: dict[str, ctk.StringVar | ctk.BooleanVar] = {}

        fields = [
            ("Server Directory",  "server_dir",      "dir",    "Folder server (berisi jar / run.bat)"),
            ("JAR Name",          "jar_name",         "str",    "Nama file jar, mis: forge-1.20-server.jar"),
            ("Start Command",     "start_command",    "str",    "Command penuh (opsional, menggantikan JAR)"),
            ("Java Path",         "java_path",        "file",   "Path java.exe, atau 'java' jika sudah di PATH"),
            ("Java Args",         "java_args",        "str",    "JVM flags, mis: -Xmx4G -Xms4G"),
            ("Stop Command",      "stop_command",     "str",    "Command untuk stop server (default: stop)"),
            ("Stop Timeout (s)",  "stop_timeout",     "str",    "Detik tunggu graceful stop sebelum force kill"),
            ("playit.exe Path",   "playit_path",      "file",   "Path ke playit.exe CLI"),
            ("playit Autostart",  "playit_autostart", "bool",   "Jalankan playit otomatis saat server start"),
            ("playit Enabled",    "playit_enabled",   "bool",   "Aktifkan integrasi playit.gg"),
            ("Theme",             "theme",            "choice", "dark / light / system"),
        ]

        row = 0
        for label, key, ftype, hint in fields:
            ctk.CTkLabel(parent, text=label + ":", anchor="e", width=160).grid(
                row=row, column=0, sticky="e", padx=(10, 6), pady=4)
            ctk.CTkLabel(parent, text=hint, text_color=C_GRAY, anchor="w", font=("", 10)).grid(
                row=row+1, column=0, columnspan=4, sticky="w", padx=(16, 4), pady=0)

            if ftype == "bool":
                v = ctk.BooleanVar(value=bool(cfg.get(key, False)))
                self._svar[key] = v
                ctk.CTkSwitch(parent, text="", variable=v).grid(row=row, column=1, sticky="w", padx=4, pady=4)
            elif ftype == "choice":
                choices = ["dark", "light", "system"]
                v = ctk.StringVar(value=str(cfg.get(key, "dark")))
                self._svar[key] = v
                ctk.CTkOptionMenu(parent, values=choices, variable=v, width=120).grid(
                    row=row, column=1, sticky="w", padx=4, pady=4)
            else:
                v = ctk.StringVar(value=str(cfg.get(key, "")))
                self._svar[key] = v
                ent = ctk.CTkEntry(parent, textvariable=v)
                ent.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
                if ftype in ("dir", "file"):
                    is_dir = ftype == "dir"
                    btn = ctk.CTkButton(parent, text="📂", width=36,
                                        command=lambda k=key, d=is_dir: self._browse(k, d))
                    btn.grid(row=row, column=2, padx=2, pady=4)
            row += 2

        # detect from run.bat button
        ctk.CTkButton(parent, text="⚙ Auto-detect dari run.bat",
                      command=self._auto_detect).grid(row=row, column=0, columnspan=2,
                                                      sticky="w", padx=10, pady=8)
        row += 1

        # save button
        ctk.CTkButton(parent, text="💾 Simpan Settings", fg_color=C_BLUE,
                      command=self._save_settings).grid(row=row, column=0, columnspan=2,
                                                        sticky="w", padx=10, pady=4)
        self.lbl_settings_status = ctk.CTkLabel(parent, text="", text_color=C_GREEN)
        self.lbl_settings_status.grid(row=row+1, column=0, columnspan=3, sticky="w", padx=10)

    def _browse(self, key: str, is_dir: bool) -> None:
        if is_dir:
            path = filedialog.askdirectory(title="Pilih folder")
        else:
            path = filedialog.askopenfilename(title="Pilih file")
        if path and key in self._svar:
            self._svar[key].set(path)

    def _auto_detect(self) -> None:
        server_dir = self._svar.get("server_dir")
        if server_dir:
            self.config_obj.set("server_dir", server_dir.get())
        found = self.config_obj.auto_detect_from_runbat()
        if found:
            for k, v in found.items():
                if k in self._svar:
                    self._svar[k].set(v)
            self.lbl_settings_status.configure(
                text=f"✓ Detected: {', '.join(found.keys())}", text_color=C_GREEN)
        else:
            self.lbl_settings_status.configure(text="run.bat / user_jvm_args.txt tidak ditemukan.",
                                               text_color=C_ORANGE)

    def _save_settings(self) -> None:
        for key, v in self._svar.items():
            val = v.get()
            if key == "stop_timeout":
                try:
                    val = int(val)
                except ValueError:
                    val = 60
            self.config_obj.set(key, val)
        self.config_obj.save()
        ctk.set_appearance_mode(self.config_obj.get("theme", "dark"))
        self.lbl_settings_status.configure(text="✓ Settings disimpan.", text_color=C_GREEN)
        self.after(3000, lambda: self.lbl_settings_status.configure(text=""))

    # ── commands ──────────────────────────────────────────────────────────────

    def _cmd_start(self) -> None:
        # start playit if enabled and autostart
        if (self.config_obj.get("playit_enabled") and
                self.config_obj.get("playit_autostart") and
                not self.playit.is_running):
            p_path = self.config_obj.get("playit_path", "")
            if p_path:
                ok, msg = self.playit.start(p_path)
                self._log_ui(f"[PLAYIT] {msg}")

        ok, msg = self.server.start()
        self._log_ui(f"[SERVER] {msg}")
        if not ok:
            messagebox.showerror("Start Error", msg)

    def _cmd_stop(self) -> None:
        self.btn_stop.configure(state="disabled")
        self.btn_restart.configure(state="disabled")
        self._log_ui("[SERVER] Stopping...")
        self.server.stop_async(done_cb=lambda: self._after_main(self._update_buttons))
        if self.playit.is_running:
            threading.Thread(target=self._delayed_playit_stop, daemon=True).start()

    def _delayed_playit_stop(self) -> None:
        time.sleep(3)
        self.playit.stop()

    def _cmd_restart(self) -> None:
        self.btn_stop.configure(state="disabled")
        self.btn_restart.configure(state="disabled")
        self._log_ui("[SERVER] Restarting...")
        self.server.restart_async(done_cb=lambda: self._after_main(self._update_buttons))

    def _send_command(self, event=None) -> None:
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        if self.server.send_command(cmd):
            self._log_ui(f"> {cmd}")
        else:
            self._log_ui("[SERVER] Server tidak berjalan.")
        self.cmd_entry.delete(0, "end")

    def _clear_console(self) -> None:
        self.console_box.configure(state="normal")
        self.console_box.delete("1.0", "end")
        self.console_box.configure(state="disabled")

    # ── scheduler callbacks ───────────────────────────────────────────────────

    def _on_sched_warn(self, minutes: int) -> None:
        msg = f"§c[Auto-Shutdown] Server akan shutdown dalam {minutes} menit!"
        self.server.send_command(f"say {msg}")
        self._log_ui(f"[SCHED] Warning: {minutes} menit menuju shutdown.")

    def _on_sched_shutdown(self) -> None:
        self._log_ui("[SCHED] Waktu shutdown! Menghentikan server + playit...")
        self.server.send_command("say §c[Auto-Shutdown] Server shutting down sekarang!")
        time.sleep(2)
        self.server.stop_async(done_cb=None)
        if self.playit.is_running:
            threading.Thread(target=self._delayed_playit_stop, daemon=True).start()

    # ── status callbacks ──────────────────────────────────────────────────────

    def _on_server_status(self, status: str) -> None:
        self._after_main(lambda: self._update_server_status_ui(status))

    def _update_server_status_ui(self, status: str) -> None:
        if status == "running":
            self.lbl_server_status.configure(text="● Online", text_color=C_GREEN)
        else:
            self.lbl_server_status.configure(text="● Offline", text_color=C_GRAY)
        self._update_buttons()
        self._refresh_players()

    def _on_playit_status(self, status: str) -> None:
        self._after_main(lambda: self._update_playit_ui(status))

    def _update_playit_ui(self, status: str) -> None:
        color = C_GREEN if status == "running" else C_GRAY
        self.lbl_playit.configure(text=f"playit: ●", text_color=color)

    def _on_monitor_update(self, data: dict) -> None:
        self._after_main(lambda: self._update_monitor_ui(data))

    def _update_monitor_ui(self, data: dict) -> None:
        cpu = data.get("cpu", 0.0)
        ram = data.get("ram_mb", 0.0)
        self.lbl_cpu.configure(text=f"CPU: {cpu:.1f}%")
        self.lbl_ram.configure(text=f"RAM: {ram:.0f} MB")

    def _update_buttons(self) -> None:
        running = self.server.is_running
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.btn_restart.configure(state="normal" if running else "disabled")

    # ── log / console ─────────────────────────────────────────────────────────

    def _poll_log_queue(self) -> None:
        limit = self.config_obj.get("console_buffer_lines", 2000)
        try:
            while True:
                source, text = self.log_queue.get_nowait()
                self._append_console(f"[{source}] {text}\n")
        except Empty:
            pass
        # also refresh player count periodically
        self.lbl_player_count.configure(text=f"Players online: {len(self.server.players)}")
        self.after(100, self._poll_log_queue)

    def _append_console(self, text: str) -> None:
        box = self.console_box
        box.configure(state="normal")
        box.insert("end", text)
        # trim to buffer limit
        lines = int(box.index("end-1c").split(".")[0])
        limit = int(self.config_obj.get("console_buffer_lines", 2000))
        if lines > limit:
            box.delete("1.0", f"{lines - limit}.0")
        box.configure(state="disabled")
        box.see("end")

    def _log_ui(self, text: str) -> None:
        self.log_queue.put(("UI", text))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _after_main(self, fn) -> None:
        """Schedule fn on the main thread."""
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _on_close(self) -> None:
        if self.server.is_running:
            if not messagebox.askyesno("Keluar", "Server masih berjalan. Yakin keluar?\n(Server tidak akan distop otomatis.)"):
                return
        self.monitor.stop()
        self.scheduler.stop()
        self.destroy()
