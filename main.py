"""MC Dashboard — entrypoint."""
import sys
from pathlib import Path

# ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui.app import App


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
