"""Settings screen smoke test: draw it, toggle things, check persistence."""

import json
import os
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["TESSERA_HEADLESS"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from tessera.ui.app import App, MenuScreen
from tessera.ui.settings_screen import SettingsScreen

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


def main():
    path = os.path.join(os.environ.get("APPDATA", ""), "Tessera", "settings.json")
    backup = None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            backup = handle.read()
    except OSError:
        backup = None

    app = App()
    app.screen = MenuScreen(app)
    app.screen.enter()

    screen = SettingsScreen(app)
    app.switch(screen)
    screen.draw(app.surface)
    check("menu settings screen draws", True)
    check("rules editable with no game", screen._rules_editable())

    # Change the clock and confirm it lands in app settings.
    screen.clocks.on_change(180)
    check("clock saved", app.settings["turn_seconds"] == 180, app.settings["turn_seconds"])

    # Hints toggle off, then check a local game respects it.
    screen.hints.on_change(False)
    check("hints saved", app.settings["allow_hints"] is False)

    screen.highlight.on_change(False)
    check("highlight saved", app.settings["highlight_last_move"] is False)

    screen.go_back()
    check("back goes to the menu", isinstance(app.screen, MenuScreen))

    path = os.path.join(os.environ.get("APPDATA", ""), "Tessera", "settings.json")
    saved = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
    except OSError:
        pass
    check("settings written to disk", saved.get("turn_seconds") == 180, saved)

    # Start a local game with hints off and confirm the server refuses hints.
    app.start_local("Tester", [1], 180, True)
    time.sleep(1.0)
    snapshot = app.client.snapshot
    check("game started", bool(snapshot and snapshot.get("state")))
    check("allow_hints propagated", snapshot["settings"].get("allow_hints") is False, snapshot["settings"])
    app.client.ask_hint()
    start = time.time()
    while time.time() - start < 5 and not app.client.errors:
        time.sleep(0.1)
    check("hint request refused", any("Hints" in error for error in app.client.errors), app.client.errors)

    # Esc from the game opens settings, locked.
    game = app.screen
    game.update(0.016)
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0))
    check("Esc opens settings from the game", isinstance(app.screen, SettingsScreen), type(app.screen).__name__)
    if isinstance(app.screen, SettingsScreen):
        check("match rules locked during play", not app.screen._rules_editable())
        app.screen.draw(app.surface)
        check("locked settings screen draws", True)
        app.screen.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0))
        check("Esc returns to the game", app.screen is game, type(app.screen).__name__)

    app.leave_game()

    # Put the user's settings file back the way it was.
    try:
        if backup is None:
            os.remove(path)
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(backup)
    except OSError:
        pass

    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
