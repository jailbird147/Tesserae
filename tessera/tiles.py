"""Tile set and board constants for English (CSW24) Scrabble."""

from __future__ import annotations

from dataclasses import dataclass

BOARD_SIZE = 15
RACK_SIZE = 7
BINGO_BONUS = 50
CENTER = 7

LETTER_VALUES = {
    "A": 1, "B": 3, "C": 3, "D": 2, "E": 1, "F": 4, "G": 2, "H": 4, "I": 1,
    "J": 8, "K": 5, "L": 1, "M": 3, "N": 1, "O": 1, "P": 3, "Q": 10, "R": 1,
    "S": 1, "T": 1, "U": 1, "V": 4, "W": 4, "X": 8, "Y": 4, "Z": 10, "?": 0,
}

LETTER_COUNTS = {
    "A": 9, "B": 2, "C": 2, "D": 4, "E": 12, "F": 2, "G": 3, "H": 2, "I": 9,
    "J": 1, "K": 1, "L": 4, "M": 2, "N": 6, "O": 8, "P": 2, "Q": 1, "R": 6,
    "S": 4, "T": 6, "U": 4, "V": 2, "W": 2, "X": 1, "Y": 2, "Z": 1, "?": 2,
}

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Standard Scrabble premium squares, zero-indexed.
_TRIPLE_WORD = {
    (0, 0), (0, 7), (0, 14),
    (7, 0), (7, 14),
    (14, 0), (14, 7), (14, 14),
}
_DOUBLE_WORD = {
    (7, 7),  # centre star
    (1, 1), (2, 2), (3, 3), (4, 4),
    (1, 13), (2, 12), (3, 11), (4, 10),
    (13, 1), (12, 2), (11, 3), (10, 4),
    (13, 13), (12, 12), (11, 11), (10, 10),
}
_TRIPLE_LETTER = {
    (1, 5), (1, 9),
    (5, 1), (5, 5), (5, 9), (5, 13),
    (9, 1), (9, 5), (9, 9), (9, 13),
    (13, 5), (13, 9),
}
_DOUBLE_LETTER = {
    (0, 3), (0, 11),
    (2, 6), (2, 8),
    (3, 0), (3, 7), (3, 14),
    (6, 2), (6, 6), (6, 8), (6, 12),
    (7, 3), (7, 11),
    (8, 2), (8, 6), (8, 8), (8, 12),
    (11, 0), (11, 7), (11, 14),
    (12, 6), (12, 8),
    (14, 3), (14, 11),
}

BOARD_PREMIUMS: dict[tuple[int, int], str] = {}
for _square in _TRIPLE_WORD:
    BOARD_PREMIUMS[_square] = "TW"
for _square in _DOUBLE_WORD:
    BOARD_PREMIUMS[_square] = "DW"
for _square in _TRIPLE_LETTER:
    BOARD_PREMIUMS[_square] = "TL"
for _square in _DOUBLE_LETTER:
    BOARD_PREMIUMS[_square] = "DL"

CENTER_SQUARE = (CENTER, CENTER)


@dataclass(frozen=True)
class Tile:
    letter: str          # "?" for a blank
    is_blank: bool = False

    @property
    def score(self) -> int:
        return 0 if self.is_blank else LETTER_VALUES[self.letter]

    @property
    def label(self) -> str:
        return self.letter


def full_bag() -> list[str]:
    bag: list[str] = []
    for letter, count in LETTER_COUNTS.items():
        bag.extend([letter] * count)
    return bag


def letter_value(letter: str) -> int:
    return LETTER_VALUES.get(letter.upper(), 0)
