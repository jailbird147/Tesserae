"""Bot opponents: Quackle's players plus a little human imperfection."""

from __future__ import annotations

import random

from .board import Board, PlayError
from .engine import Move, QuackleEngine, shared_engine
from .tiles import CENTER, LETTER_VALUES

# Each level has five dials:
#   pool         how many of Quackle's moves it will consider
#   sharp        chance it simply takes the best one
#   weak         chance it settles for a cheap small play instead
#   weak_ceiling the most points such a play may score
#   bingo_miss   chance it ignores a seven-tile play
#   exchange     chance it swaps tiles instead of playing, when the bag allows
#
# The weak dials are what make the low levels genuinely beatable: a move that
# is cheap on purpose is nothing like "the eighth best move Quackle found".
LEVELS = [
    {
        "level": 1,
        "name": "Rookie",
        "seconds": 1,
        "blurb": "Short, low-scoring words. Misses bingos and good squares.",
        "pool": 24,
        "sharp": 0.03,
        "weak": 0.93,
        "weak_ceiling": 14,
        "bingo_miss": 0.85,
        "exchange": 0.12,
    },
    {
        "level": 2,
        "name": "Casual",
        "seconds": 1,
        "blurb": "Finds solid words, weak strategy and leaves.",
        "pool": 14,
        "sharp": 0.2,
        "weak": 0.58,
        "weak_ceiling": 20,
        "bingo_miss": 0.35,
        "exchange": 0.05,
    },
    {
        "level": 3,
        "name": "Club",
        "seconds": 2,
        "blurb": "Simulates a few lines. Club standard.",
        "pool": 6,
        "sharp": 0.7,
        "weak": 0.22,
        "weak_ceiling": 26,
        "bingo_miss": 0.05,
        "exchange": 0.0,
    },
    {
        "level": 4,
        "name": "Expert",
        "seconds": 4,
        "blurb": "Strong leaves and endgames.",
        "pool": 2,
        "sharp": 0.99,
        "weak": 0.0,
        "bingo_miss": 0.0,
        "exchange": 0.0,
    },
    {
        "level": 5,
        "name": "Master",
        "seconds": 8,
        "blurb": "Quackle's championship player.",
        "pool": 1,
        "sharp": 1.0,
        "weak": 0.0,
        "bingo_miss": 0.0,
        "exchange": 0.0,
    },
]


def level_info(level: int) -> dict:
    return LEVELS[max(1, min(5, level)) - 1]


def _pick(moves: list[Move], level: int, rng: random.Random) -> Move | None:
    if not moves:
        return None
    info = level_info(level)
    pool = moves[: info["pool"]]

    # Weak players miss the bingo they could have played.
    if info.get("bingo_miss") and rng.random() < info["bingo_miss"]:
        shorter = [move for move in pool if len(move.word) < 7]
        if shorter:
            pool = shorter

    # And plenty of the time they settle for something cheap, even though a
    # much better play is right there. This is the main difference between a
    # beginner and Quackle: not a worse engine, a worse choice.
    ceiling = info.get("weak_ceiling")
    if ceiling and len(moves) > 1 and rng.random() < info["weak"]:
        cheap = sorted((move for move in moves if move.score <= ceiling),
                       key=lambda move: move.score)
        if cheap:
            return rng.choice(cheap[: max(3, len(cheap) // 2)])

    if len(pool) == 1 or rng.random() < info["sharp"]:
        return pool[0]
    weights = [1.0 / (i + 1) for i in range(len(pool))]
    total = sum(weights)
    roll = rng.uniform(0, total)
    upto = 0.0
    for move, weight in zip(pool, weights):
        upto += weight
        if roll <= upto:
            return move
    return pool[-1]


def fallback_move(board: Board, rack: list[str], lexicon) -> list[tuple[int, int, str, bool]] | None:
    """Tiny move finder used only if the Quackle engine cannot run."""
    if not rack:
        return None

    anchors: set[tuple[int, int]] = set()
    if board.is_empty():
        anchors.add((CENTER, CENTER))
    else:
        for row in range(15):
            for col in range(15):
                if board.grid[row][col] is not None:
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nr, nc = row + dr, col + dc
                        if 0 <= nr < 15 and 0 <= nc < 15 and board.grid[nr][nc] is None:
                            anchors.add((nr, nc))

    best: tuple[int, list[tuple[int, int, str, bool]]] | None = None
    letters = [letter for letter in rack if letter != "?"]
    for row, col in anchors:
        for letter in letters:
            try:
                result = board.score_play({(row, col): (letter, False)}, lexicon)
            except PlayError:
                continue
            if best is None or result.score > best[0]:
                best = (result.score, [(row, col, letter, False)])

    if best is None and "?" in rack:
        letters_any = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for row, col in anchors:
            for letter in letters_any:
                try:
                    result = board.score_play({(row, col): (letter, True)}, lexicon)
                except PlayError:
                    continue
                if best is None or result.score > best[0]:
                    best = (result.score, [(row, col, letter, True)])
    return best[1] if best else None


def choose_bot_action(
    board: Board,
    rack: list[str],
    bag: list[str],
    my_score: int,
    opp_score: int,
    level: int,
    lexicon,
    engine: QuackleEngine | None = None,
    rng: random.Random | None = None,
) -> tuple[str, object]:
    """Return ("play", cells) / ("exchange", letters) / ("pass", None)."""
    rng = rng or random.Random()
    info = level_info(level)

    # A beginner will sometimes swap tiles that look awkward rather than work
    # around them.
    if info.get("exchange") and len(bag) >= 7 and rack and rng.random() < info["exchange"]:
        ordered = sorted(rack, key=lambda letter: (LETTER_VALUES.get(letter, 0), letter))
        return "exchange", ordered[: min(4, len(ordered))]

    engine = engine or shared_engine()
    moves: list[Move] = []
    if engine.available():
        try:
            engine.ensure_started()
            moves = engine.moves(
                board_grid=board.grid_string(),
                rack=rack,
                bag=bag,
                my_score=my_score,
                opp_score=opp_score,
                level=info["level"],
                seconds=info["seconds"],
                # Weak levels need a long list: the cheap plays a beginner
                # would find are nowhere near Quackle's best twenty.
                top=max(80, info["pool"] * 4),
            )
        except Exception:
            moves = []

    move = _pick(moves, level, rng)
    if move is not None:
        cells = move.placements
        if cells:
            return "play", cells

    fallback = fallback_move(board.clone(), list(rack), lexicon)
    if fallback:
        return "play", fallback

    if len(bag) >= 7 and rack:
        ordered = sorted(rack, key=lambda letter: (LETTER_VALUES.get(letter, 0), letter), reverse=True)
        return "exchange", ordered[: min(3, len(ordered))]
    return "pass", None
