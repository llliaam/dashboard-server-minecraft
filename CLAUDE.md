# MC Dashboard — Project Instructions

Desktop app (Windows-native, **bukan web**) untuk manage Minecraft server lokal + playit.gg, dengan auto-shutdown terjadwal.

## Keputusan final (JANGAN diubah tanpa konfirmasi user)

| Aspek | Pilihan | Implikasi |
|---|---|---|
| Shutdown scope | **Server + playit saja** | PC TETAP nyala. `shutdown_pc` dikunci `false`. |
| Tipe server | **Forge/Fabric (modded)** | Pakai **stdin/stdout piping**, BUKAN RCON. Universal. |
| Stack | **Python + CustomTkinter** | Native window. Deps: `customtkinter`, `psutil`. |
| playit | **CLI `playit.exe`** | Dikontrol sebagai child process (start/kill). |
| Player mgmt | **List + Kick + Ban/Unban + Whitelist** | Semua via command ke stdin. |
| Backup dunia | **v2 (skip untuk sekarang)** | Ditambah belakangan. |

## Aturan wajib

- **NO HARDCODE.** Semua path & jadwal dari tab Settings → `config.json`.
  Configurable: `server_dir`, `java_path`, `java_args`, `jar_name` atau `start_command`,
  `playit_path`, `stop_timeout`, jadwal, warn_minutes.
- UI **tidak pernah blok** — semua operasi berat (baca log, tunggu proses mati) di thread background,
  komunikasi ke UI lewat thread-safe queue.
- Server via `subprocess.Popen(stdin=PIPE, stdout=PIPE)`. Command dikirim ke stdin, log dibaca dari stdout.
- Console encoding: `errors="replace"` (modded server kadang non-UTF8).
- Graceful stop: kirim `save-all` → `stop` → tunggu `stop_timeout` (default 60s) → `terminate()` → `kill()`.

## Arsitektur

```
UI (main thread) ── queue ──> Core (background threads)
Tabs: Console | Players | Scheduler | Settings
Core: ServerManager | PlayitManager | Scheduler | Monitor | Config | Properties
```

## Fitur & cara kerja

- **Start/Stop/Restart**: start = playit (jika autostart) → java. stop = graceful + timeout → force kill → matiin playit.
- **Console + command**: TextBox live stdout; input box → stdin.
- **Player list**: parse log `<Player> joined/left the game`. Kick/ban/whitelist via stdin command.
- **Monitor**: `psutil` poll PID java tiap ~2s → % CPU & MB RAM.
- **Editor server.properties**: baca/tulis `key=value` (butuh restart server agar berlaku).
- **Scheduler auto-shutdown** ⭐: cek jam tiap ~20s. Warning in-game (`say`) di menit ke-5 & 1, lalu graceful stop server + kill playit. PC TIDAK dimatikan.
- Bonus: auto-detect args dari `run.bat`/`user_jvm_args.txt` (Forge) saat pilih folder.

## Struktur file

```
mc-dashboard/
├─ main.py                 # entrypoint
├─ requirements.txt  start.bat  README.md
├─ config.json             # dibuat otomatis
├─ core/
│  ├─ config.py  server_manager.py  playit_manager.py
│  ├─ scheduler.py  monitor.py  properties.py
└─ ui/
   └─ app.py                # window + semua tab
```

## Risiko diketahui

1. Force kill saat hang → risiko korup chunk. Mitigasi: `save-all` dulu, timeout panjang.
2. playit.exe pertama kali butuh klaim link manual sekali (interaksi terminal).
3. Fabric & Forge format log join/leave sama → player-parsing aman keduanya.
