"""Play a whole game through the UI layer and check the end-game screens."""

import os
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["TESSERA_HEADLESS"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.engine import shared_engine
from tessera.ui.app import App, ResultsScreen
from tessera.ui.game_screen import GameScreen

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


def main():
    app = App()
    app.start_local("You", [1], 60, True)
    engine = shared_engine()
    engine.ensure_started()
    screen = app.screen
    start = time.time()
    turns_played = 0

    while time.time() - start < 420:
        snapshot = app.client.snapshot if app.client else None
        if not snapshot or not snapshot.get("state"):
            time.sleep(0.1)
            continue
        state = snapshot["state"]
        if state["game_over"]:
            break
        if not isinstance(app.screen, GameScreen):
            app.screen.update(0.016)
        screen = app.screen
        if isinstance(screen, GameScreen):
            screen.update(0.016)
            if isinstance(app.screen, ResultsScreen):
                break
            if state.get("current") == app.client.seat and not screen.locked:
                rack = state["players"][app.client.seat]["rack"]
                grid = "".join(
                    "." if cell is None else (cell[0].lower() if cell[1] else cell[0])
                    for row in state["board"] for cell in row
                )
                moves = engine.moves(grid, rack, "AEIOULNSTR" * 8, state["players"][app.client.seat]["score"],
                                     max(p["score"] for p in state["players"] if p["seat"] != app.client.seat),
                                     level=1, seconds=1, top=6)
                if moves:
                    cells = moves[0].placements
                    screen.pending.clear()
                    used = set()
                    ok = True
                    for row, col, letter, blank in cells:
                        choice = None
                        for index, tile in enumerate(screen._rack()):
                            if index in used:
                                continue
                            if (blank and tile == "?") or (not blank and tile == letter):
                                choice = index
                                break
                        if choice is None:
                            ok = False
                            break
                        used.add(choice)
                        screen.pending[(row, col)] = (letter, bool(blank), choice)
                    if ok:
                        screen.do_play()
                        turns_played += 1
                    else:
                        screen.pending.clear()
                        app.client.pass_turn()
                        screen.locked = True
                else:
                    app.client.pass_turn()
                    screen.locked = True
        time.sleep(0.35)

    snapshot = app.client.snapshot
    state = snapshot["state"]
    check("game finished", state["game_over"], state["turn"])
    check("human turns played", turns_played > 3, turns_played)
    time.sleep(0.5)
    if isinstance(app.screen, GameScreen):
        app.screen.update(0.016)
    check("results screen shown", isinstance(app.screen, ResultsScreen), type(app.screen).__name__)
    print("final scores:", [(p["name"], p["score"], p["tiles_left"]) for p in state["players"]])
    for record in state["history"][-6:]:
        print("  ", record["turn"], record["name"], record["kind"], record["detail"], record["score"])
    print("result:", state["result"])

    # Post-game analysis through the results screen.
    from tessera.ui.analysis_screen import AnalysisScreen
    if isinstance(app.screen, ResultsScreen):
        app.client.analysis = None
        app.screen.do_analysis()
        check("analysis screen opened", isinstance(app.screen, AnalysisScreen), type(app.screen).__name__)
        start = time.time()
        while time.time() - start < 120:
            analysis = app.client.analysis
            if analysis and analysis.get("phase") in ("done", "error"):
                break
            time.sleep(0.2)
        analysis = app.client.analysis
        check("analysis finished", bool(analysis and analysis.get("phase") == "done"), analysis)
        if analysis and analysis.get("phase") == "done":
            rows = analysis["data"]["moves"]
            check("analysis has our moves", len(rows) >= 3, len(rows))
            check("analysis rows have verdicts", all("verdict" in row for row in rows))
            app.screen.draw(app.surface)
            check("analysis screen draws", True)

    app.leave_game()
    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
