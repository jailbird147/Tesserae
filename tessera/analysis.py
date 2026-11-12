"""Helpers for post-game analysis."""

from __future__ import annotations

from .tiles import BOARD_SIZE


def main_word_pattern(board_before: str, cells: list[tuple[int, int, str, bool]]):
    """Work out the full word a play belongs to, as a Quackle tile pattern.

    Returns (row, col, horizontal, pattern) where the pattern uses '.' for
    letters already on the board and lowercase for a blank. Returns None if the
    cells are not in a single line.
    """
    if not cells:
        return None

    rows = {row for row, _col, _letter, _blank in cells}
    cols = {col for _row, col, _letter, _blank in cells}
    if len(rows) > 1 and len(cols) > 1:
        return None
    horizontal = len(rows) == 1

    grid = list(board_before) if len(board_before) == BOARD_SIZE * BOARD_SIZE else ["."] * (BOARD_SIZE * BOARD_SIZE)

    def filled(row: int, col: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE and grid[row * BOARD_SIZE + col] != "."

    placed = {(row, col): (letter.upper(), blank) for row, col, letter, blank in cells}

    if horizontal:
        row = next(iter(rows))
        start = min(cols)
        end = max(cols)
        while filled(row, start - 1):
            start -= 1
        while filled(row, end + 1):
            end += 1
        parts = []
        for col in range(start, end + 1):
            if (row, col) in placed:
                letter, blank = placed[(row, col)]
                parts.append(letter.lower() if blank else letter)
            else:
                parts.append(".")
        return row, start, True, "".join(parts)

    col = next(iter(cols))
    start = min(rows)
    end = max(rows)
    while filled(start - 1, col):
        start -= 1
    while filled(end + 1, col):
        end += 1
    parts = []
    for row in range(start, end + 1):
        if (row, col) in placed:
            letter, blank = placed[(row, col)]
            parts.append(letter.lower() if blank else letter)
        else:
            parts.append(".")
    return start, col, False, "".join(parts)


def classify(loss: float) -> str:
    if loss <= 1.0:
        return "Best"
    if loss <= 4.0:
        return "Good"
    if loss <= 10.0:
        return "Inaccuracy"
    if loss <= 18.0:
        return "Mistake"
    return "Blunder"


def estimate_rating(average_loss: float) -> str:
    if average_loss <= 2.5:
        return "1850+"
    if average_loss <= 4.0:
        return "1700-1850"
    if average_loss <= 6.0:
        return "1550-1700"
    if average_loss <= 9.0:
        return "1400-1550"
    if average_loss <= 13.0:
        return "1250-1400"
    return "under 1250"
