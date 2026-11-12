"""Bot levels: the engine answers, and the low levels really are weak.

The point of this test is the difficulty gap. It asks each level for its move
on the same position several times and checks that Rookie picks clearly cheaper
plays than Club, so "Rookie" cannot quietly drift back to strong play.
"""

import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.board import Board
from tessera.bot import choose_bot_action, level_info
from tessera.engine import QuackleEngine
from tessera.lexicon import load_lexicon
from tessera.rules import GameState

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


lexicon = load_lexicon()
engine = QuackleEngine()
engine.ensure_started()
print("started", engine.last_error)

moves = engine.moves("." * 225, "AEIRST?", "ABCDEFGH", 0, 0, level=1, seconds=2, top=5)
print("empty-board moves", len(moves))
for move in moves:
    print(" ", move.word, move.score, move.placements)

state = GameState(["A", "B"], bots=[True, True], levels=[3, 3], lexicon=lexicon)
print("rack", state.players[0].rack, "bag", len(state.bag))
start = time.time()
moves = engine.moves(state.board.grid_string(), state.players[0].rack, state.bag, 0, 0, level=1, seconds=2, top=10)
print("real moves", len(moves), "%.2fs" % (time.time() - start), [m.word for m in moves[:6]])
print("last_error", engine.last_error)

# A position with plenty of room, so every level has something to choose from.
grid = Board()
grid.import_cells([(7, 7, "T", False), (7, 8, "O", False), (7, 9, "F", False), (7, 10, "T", False)])
rack = ["A", "E", "I", "R", "S", "N", "D"]
scores: dict[int, list[int]] = {1: [], 2: [], 3: []}
words: dict[int, list[str]] = {1: [], 2: [], 3: []}

for level in (1, 2, 3):
    for seed in range(6):
        action, payload = choose_bot_action(
            grid.clone(), list(rack), ["B", "C", "D", "E", "F", "G", "H", "I"] * 3,
            50, 50, level, lexicon, engine=engine, rng=random.Random(seed),
        )
        if action == "play":
            result = grid.score_play({(row, col): (letter, blank) for row, col, letter, blank in payload},
                                     lexicon)
            scores[level].append(result.score)
            words[level].append(result.words[0][0] if result.words else "")

for level in (1, 2, 3):
    info = level_info(level)
    print(f"level {level} ({info['name']}): {scores[level]}  mean "
          f"{statistics.mean(scores[level]) if scores[level] else 0:.1f}")

rookie = statistics.mean(scores[1]) if scores[1] else 0
club = statistics.mean(scores[3]) if scores[3] else 0
check("rookie played at all", bool(scores[1]), scores[1])
check("rookie is much cheaper than club", rookie < club * 0.75, (round(rookie, 1), round(club, 1)))
check("rookie is beatable", rookie < 20, round(rookie, 1))
