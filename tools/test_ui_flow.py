"""Exercise the UI layer's game flow without a window."""

import os
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["TESSERA_HEADLESS"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from tessera.ui.app import App
from tessera.ui.game_screen import GameScreen

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


def wait_for(predicate, timeout=20.0):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main():
    app = App()
    app.start_local("You", [2], 120, True)
    screen = app.screen
    check("game screen active", isinstance(screen, GameScreen))

    check("snapshot arrived", wait_for(lambda: app.client.snapshot is not None))
    check("game state arrived",
          wait_for(lambda: (app.client.snapshot or {}).get("state") is not None))
    screen.update(0.016)
    check("board synced", screen.board is not None)
    check("viewer sees a rack", len(screen._rack()) == 7, screen._rack())
    check("viewer seat", app.client.seat == 0, app.client.seat)

    # Place the first two letters of a word using the UI's placement path.
    rack = screen._rack()
    check("rack has 7 tiles", len(rack) == 7, rack)
    screen._place_blank  # exists
    # Use the engine to get a legal opening move, then place it tile by tile.
    from tessera.engine import shared_engine
    engine = shared_engine()
    engine.ensure_started()
    state = app.client.snapshot["state"]
    moves = []
    for seconds in (1, 2, 4):       # the first call can catch a cold engine
        moves = engine.moves("." * 225, rack, state["bag"] and "AEIOULNSTR" * 8, 0, 0,
                             level=1, seconds=seconds, top=3)
        if moves:
            break
    check("engine returned opening moves", bool(moves), rack)
    if not moves:
        app.leave_game()
        print()
        print("FAILURES:", failures)
        return 1
    # Rack order is the player's own: dragging a tile slides it, and a tile
    # already waiting on the board stays attached to its letter.
    screen.rack_order = list(range(len(screen._rack())))
    first_letter = screen._rack()[0]
    screen.move_rack_tile(0, 4)
    check("tile slid along the rack", screen._rack()[4] == first_letter, screen._rack())
    screen.move_rack_tile(4, 0)
    check("tile slid back", screen._rack()[0] == first_letter, screen._rack())

    cells = moves[0].placements
    mapping = screen.map_cells_to_rack(cells)
    check("engine move fits the rack", mapping is not None)
    placed = 0
    for row, col, letter, blank, choice in mapping or []:
        screen._place(row, col, choice)
        if screen.modal == "blank":       # the rack tile is a blank
            screen._place_blank(letter)
        placed += 1
    check("tiles placed on the board", len(screen.pending) == placed, (placed, len(screen.pending)))
    result, problem = screen._preview()
    check("preview is legal", result is not None, problem)

    before_turn = app.client.snapshot["state"]["turn"]
    screen.do_play()
    check("play accepted by server",
          wait_for(lambda: app.client.snapshot["state"]["turn"] != before_turn), app.client.snapshot["state"]["turn"])

    screen.update(0.016)
    check("pending cleared after the turn", not screen.pending)
    check("score recorded", app.client.snapshot["state"]["players"][0]["score"] > 0,
          app.client.snapshot["state"]["players"][0]["score"])

    # Wait for the bot to move.
    check("bot took its turn",
          wait_for(lambda: app.client.snapshot["state"]["current"] == 0, 30), app.client.snapshot["state"]["current"])

    # Hint round trip.
    screen.update(0.016)
    screen.do_hint()
    got_hint = wait_for(lambda: bool(app.client.hints) or bool(screen.hints), 30)
    check("hint returned", got_hint)

    # Pass.
    before_turn = app.client.snapshot["state"]["turn"]
    screen.do_pass()
    check("pass accepted",
          wait_for(lambda: app.client.snapshot["state"]["turn"] != before_turn), "no change")

    # Exchange through the UI: wait for our turn, pick two tiles, confirm.
    check("our turn again", wait_for(lambda: app.client.snapshot["state"]["current"] == app.client.seat, 40))
    screen.update(0.016)
    screen.toggle_exchange()
    check("exchange mode entered", screen.exchange_mode)
    if screen.exchange_mode:
        screen.exchange_selection = {0, 1}
        before_turn = app.client.snapshot["state"]["turn"]
        before_rack = sorted(screen._rack())
        screen.toggle_exchange()
        check("exchange accepted",
              wait_for(lambda: app.client.snapshot["state"]["turn"] != before_turn, 15), "no change")
        check("rack changed after exchange",
              sorted(app.client.snapshot["state"]["players"][app.client.seat]["rack"]) != before_rack)

    app.leave_game()
    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
