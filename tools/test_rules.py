"""Rule tests: scoring, validation, exchange, end of game."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.board import Board, PlayError
from tessera.lexicon import load_lexicon
from tessera.rules import GameState, RulesError
from tessera.tiles import BOARD_PREMIUMS, full_bag

LEX = load_lexicon()
failures = []


def check(name, condition, detail=""):
    if condition:
        print("ok  ", name)
    else:
        print("FAIL", name, detail)
        failures.append(name)


def expect_error(name, fn):
    try:
        fn()
    except (PlayError, RulesError):
        print("ok  ", name)
        return
    print("FAIL", name, "(no error)")
    failures.append(name)


def test_tiles():
    bag = full_bag()
    check("bag has 100 tiles", len(bag) == 100, len(bag))
    check("two blanks", bag.count("?") == 2)
    check("127 two letter words", len([w for w in LEX.words if len(w) == 2]) == 127)
    counts = {}
    for value in BOARD_PREMIUMS.values():
        counts[value] = counts.get(value, 0) + 1
    check("premium counts", counts == {"TW": 8, "DW": 17, "TL": 12, "DL": 24}, counts)
    # centre square is a double word square in the layout
    check("centre is DW", BOARD_PREMIUMS.get((7, 7)) in (None, "DW"))


def test_first_move():
    board = Board()
    result = board.score_play({(7, 7): ("H", False), (7, 8): ("E", False), (7, 9): ("L", False),
                               (7, 10): ("L", False), (7, 11): ("O", False)}, LEX)
    # H4 + E1 + L1 + L1 + O1, with the O on a double letter square, doubled by the centre
    check("hello down the middle", result.score == 18, result.score)
    check("hello words", [w for w, _ in result.words] == ["HELLO"], result.words)

    board2 = Board()
    expect_error("first move must hit centre", lambda: board2.score_play({(0, 0): ("A", False), (0, 1): ("T", False)}, LEX))

    board3 = Board()
    expect_error("not a word", lambda: board3.score_play({(7, 7): ("Z", False), (7, 8): ("Z", False)}, LEX))

    board4 = Board()
    expect_error("must be in a line", lambda: board4.score_play({(7, 6): ("A", False), (8, 7): ("T", False)}, LEX))


def test_cross_words():
    board = Board()
    board.import_cells([(7, 7, "C", False), (7, 8, "A", False), (7, 9, "T", False),
                        (8, 7, "A", False), (9, 7, "R", False)])
    # place S at (7, 10) making CATS and ...S
    result = board.score_play({(7, 10): ("S", False)}, LEX)
    words = sorted(w for w, _ in result.words)
    check("cross words found", words == ["CATS"], words)
    # The centre square is already covered, so no word multiplier: C3 + A1 + T1 + S1 = 6
    check("cross word score", result.score == 6, result.score)


def test_blank_and_bingo():
    board = Board()
    cells = {(7, 5): ("Q", True), (7, 6): ("U", False), (7, 7): ("I", False),
             (7, 8): ("C", False), (7, 9): ("K", False), (7, 10): ("E", False), (7, 11): ("R", False)}
    result = board.score_play(cells, LEX)
    # Q blank 0 + U1 + I1 + C3 + K5 + E1 + R1(on a double letter) = 13, x2 at centre, + 50 bingo
    check("blank scores zero and bingo", result.score == 76, result.score)
    check("bingo flag", result.bingo)


def test_rule_variants():
    board = Board()
    cells = {(7, 5): ("Q", True), (7, 6): ("U", False), (7, 7): ("I", False),
             (7, 8): ("C", False), (7, 9): ("K", False), (7, 10): ("E", False), (7, 11): ("R", False)}
    no_bingo = board.score_play(cells, LEX, bingo_bonus=False)
    check("bingo bonus can be switched off", no_bingo.score == 26, no_bingo.score)
    check("bingo flag off", not no_bingo.bingo)

    state = GameState(["A", "B"], bots=[True, True], levels=[1, 1], lexicon=LEX,
                      minimum_word_length=3)
    state.players[0].rack = ["A", "T", "X", "Y", "Z", "Q", "J"]
    expect_error("minimum word length enforced",
                 lambda: state.play(0, [(7, 7, "A", False), (7, 8, "T", False)]))


def test_game_flow():
    state = GameState(["One", "Two"], bots=[True, True], levels=[1, 1], lexicon=LEX)
    check("racks drawn", all(len(p.rack) == 7 for p in state.players))
    check("bag left", len(state.bag) == 86, len(state.bag))

    seat = state.current
    state.players[seat].rack = ["A", "T", "X", "Y", "Z", "Q", "J"]
    state.play(seat, [(7, 7, "A", False), (7, 8, "T", False)])
    check("turn advanced", state.current != seat)
    check("rack refilled", len(state.players[seat].rack) == 7)
    check("score added", state.players[seat].score == 4, state.players[seat].score)

    expect_error("cannot play out of turn", lambda: state.play(seat, [(0, 0, "A", False)]))


def test_endgame():
    state = GameState(["A", "B"], bots=[True, True], levels=[1, 1], lexicon=LEX)
    state.players[0].rack = []
    state.players[1].rack = list("DOG")
    state.bag = []
    state.players[0].score = 300
    state.players[1].score = 200
    state.current = 0
    state._finish(winner=state.players[0])
    check("going out collects the leftover tiles",
          state.players[0].score == 300 + 5, state.players[0].score)
    check("other player loses rack value",
          state.players[1].score == 200 - 5, state.players[1].score)


def test_blank_recycle():
    state = GameState(["A", "B"], bots=[True, True], levels=[1, 1], lexicon=LEX)
    state.players[0].rack = list("A?BCDEF")
    before = len(state.bag)
    state.recycle_blanks(0)
    check("blank leaves the rack", "?" not in state.players[0].rack)
    check("blank goes back to the bag", state.players[0].blanks_recycled)
    check("bag still has the blank", state.bag.count("?") >= 1)
    check("rack refilled", len(state.players[0].rack) == 7)
    expect_error("only once per game", lambda: state.recycle_blanks(0))


print()
tests = [test_tiles, test_first_move, test_cross_words, test_blank_and_bingo,
         test_rule_variants, test_game_flow, test_endgame, test_blank_recycle]
for test in tests:
    test()

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
