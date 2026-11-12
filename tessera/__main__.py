"""Entry point: python -m tessera"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if "--selftest" in sys.argv:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ["TESSERA_HEADLESS"] = "1"
        from .selftest import run_selftest
        return run_selftest()

    from .ui.app import App
    try:
        app = App()
    except Exception as exc:
        print(f"Could not open the game window: {exc}")
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
