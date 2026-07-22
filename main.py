"""MC Dashboard — entrypoint."""
import sys
from pathlib import Path

# ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _ensure_shortcut() -> None:
    """Create Desktop shortcut on first run (silent — never blocks startup)."""
    try:
        from create_shortcut import create, shortcut_exists
        if not shortcut_exists():
            create()
    except Exception:
        pass


def main() -> None:
    _ensure_shortcut()
    from ui.app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
