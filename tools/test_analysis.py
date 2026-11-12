"""Analysis: word patterns, and Quackle's review of a finished game."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.analysis import classify, main_word_pattern
from tessera.engine import shared_engine
from tessera.session import Session

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


def test_patterns():
    empty = "." * 225
    result = main_word_pattern(empty, [(7, 7, "A", False), (7, 8, "B", False)])
    check("horizontal pattern", result == (7, 7, True, "AB"), result)

    grid = list(empty)
    grid[7 * 15 + 6] = "C"
    result = main_word_pattern("".join(grid), [(7, 7, "A", False), (7, 8, "B", False)])
    check("play-through marked", result == (7, 6, True, ".AB"), result)

    result = main_word_pattern(empty, [(7, 7, "A", True), (8, 7, "B", False)])
    check("vertical blank pattern", result == (7, 7, False, "aB"), result)


def test_analysis():
    session = Session(turn_seconds=60, seats=2, lexicon="csw")
    session.join("Alice", "alice")
    session.join("Bob", "bob")
    session.start()
    time.sleep(0.2)

    engine = shared_engine()
    engine.ensure_started()
    state = session.state
    played = 0
    for turn_index in range(6):
        seat = state.current
        player = state.players[seat]
        moves = engine.moves(state.board.grid_string(), player.rack, state.bag, player.score, 0,
                             level=1, seconds=1, top=5)
        if not moves:
            state.pass_turn(seat)
            continue
        # Alice deliberately plays a weaker move on her second turn.
        choice = moves[-1] if seat == 0 and turn_index >= 2 else moves[0]
        state.play(seat, choice.placements)
        played += 1
        if state.game_over:
            break

    check("some moves were played", played >= 2, played)
    state._finish(winner=None)
    session.phase = "finished"

    events = []
    session.analyse("alice", events.append)
    start = time.time()
    while time.time() - start < 60:
        if any(event.get("phase") in ("done", "error") for event in events):
            break
        time.sleep(0.1)

    done = [event for event in events if event.get("phase") == "done"]
    check("analysis finished", bool(done), [e.get("phase") for e in events][-3:])
    if done:
        data = done[0]["data"]
        rows = data["moves"]
        check("analysed Alice's moves", len(rows) >= 1, len(rows))
        if rows:
            row = rows[0]
            check("best move reported", row["best"] not in ("", "?", None), row)
            check("played move scored", row["played_score"] > 0, row)
            check("equity loss computed", row["loss"] is not None, row)
            check("verdict set", row["verdict"] in ("Best", "Good", "Inaccuracy", "Mistake", "Blunder"), row["verdict"])
        summary = data["summary"]
        check("summary has counts", summary["count"] == len(rows), summary)
        check("a mistake was detected", any((row["loss"] or 0) > 0 for row in rows), [row["loss"] for row in rows])
        check("summary has a rating", isinstance(summary["rating"], str) and summary["rating"], summary["rating"])
        print("   summary:", summary)

    # Verdict bands
    check("classify best", classify(0.3) == "Best")
    check("classify blunder", classify(30) == "Blunder")

    session.close()


test_patterns()
test_analysis()
print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
