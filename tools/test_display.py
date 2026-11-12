"""Display test: full screen toggling and smooth scaling with a real window."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from tessera.ui.app import App, SIZE

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


def main():
    app = App()
    check("window opened", app.window is not None, app.window.get_size())

    # Rapidly toggle full screen on and off, exactly what used to crash.
    for _ in range(3):
        app.settings["fullscreen"] = True
        app.apply_display_preferences()
        app.screen.draw(app.canvas)
        app._present()
        app.settings["fullscreen"] = False
        app.apply_display_preferences()
        app.screen.draw(app.canvas)
        app._present()
        time.sleep(0.05)
    check("survived rapid full screen toggles", True)
    check("windowed size restored", app.window.get_size() == SIZE, app.window.get_size())

    # Scaled window: canvas is upscaled and mouse coordinates are mapped back.
    app.window = pygame.display.set_mode((1860, 1320), pygame.RESIZABLE)
    app.screen.draw(app.canvas)
    app._present()
    check("scaled present", app._view_scale > 1.0, app._view_scale)

    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (930, 660), "button": 1})
    mapped = app._map_event(event).pos
    check("mouse mapping", abs(mapped[0] - SIZE[0] / 2) < 3 and abs(mapped[1] - SIZE[1] / 2) < 3, mapped)

    # Back to the normal window and one more present, then close.
    app.window = pygame.display.set_mode(SIZE, pygame.RESIZABLE)
    app.screen.draw(app.canvas)
    app._present()
    pygame.quit()

    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
