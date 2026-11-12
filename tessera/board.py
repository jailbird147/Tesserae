"""Board model: geometry, premium squares and scoring of a play."""

from __future__ import annotations

from dataclasses import dataclass, field

from .tiles import BINGO_BONUS, BOARD_PREMIUMS, BOARD_SIZE, CENTER_SQUARE, LETTER_VALUES

Cell = tuple[str, bool] | None  # (letter, is_blank)


class PlayError(Exception):
    """Raised when a play breaks the rules."""


@dataclass
class PlayResult:
    score: int
    words: list[tuple[str, int]] = field(default_factory=list)
    bingo: bool = False
    placements: dict[tuple[int, int], Cell] = field(default_factory=dict)


def in_bounds(row: int, col: int) -> bool:
    return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE


class Board:
    def __init__(self) -> None:
        self.grid: list[list[Cell]] = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]

    # ------------------------------------------------------------------ state
    def clone(self) -> "Board":
        other = Board()
        other.grid = [row[:] for row in self.grid]
        return other

    def cell(self, row: int, col: int) -> Cell:
        return self.grid[row][col]

    def is_empty(self) -> bool:
        return all(cell is None for row in self.grid for cell in row)

    def occupied(self) -> list[tuple[int, int, str, bool]]:
        out: list[tuple[int, int, str, bool]] = []
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cell = self.grid[r][c]
                if cell is not None:
                    out.append((r, c, cell[0], cell[1]))
        return out

    def import_cells(self, cells: list[tuple[int, int, str, bool]]) -> None:
        self.grid = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        for row, col, letter, blank in cells:
            if in_bounds(row, col):
                self.grid[row][col] = (letter.upper(), bool(blank))

    def grid_string(self) -> str:
        """225 characters for the Quackle bridge: '.' empty, lowercase = blank."""
        chars = []
        for row in self.grid:
            for cell in row:
                if cell is None:
                    chars.append(".")
                else:
                    letter, blank = cell
                    chars.append(letter.lower() if blank else letter.upper())
        return "".join(chars)

    def apply(self, placements: dict[tuple[int, int], Cell]) -> None:
        for (row, col), cell in placements.items():
            if cell is not None:
                self.grid[row][col] = cell

    def remove(self, positions: list[tuple[int, int]]) -> None:
        for row, col in positions:
            self.grid[row][col] = None

    # -------------------------------------------------------------- validation
    def check_shape(self, placements: dict[tuple[int, int], Cell]) -> tuple[str, int]:
        """Validate placement geometry. Returns (orientation, fixed_index)."""
        if not placements:
            raise PlayError("Place at least one tile.")

        for row, col in placements:
            if not in_bounds(row, col):
                raise PlayError("That square is off the board.")
            if self.grid[row][col] is not None:
                raise PlayError("That square is already covered.")

        rows = {r for r, _ in placements}
        cols = {c for _, c in placements}
        if len(rows) > 1 and len(cols) > 1:
            raise PlayError("Tiles must be in one row or one column.")

        if len(placements) == 1:
            orientation = "H"
        elif len(rows) == 1:
            orientation = "H"
        else:
            orientation = "V"

        if orientation == "H":
            fixed = next(iter(rows))
            positions = sorted(c for _, c in placements)
            for col in range(positions[0], positions[-1] + 1):
                if (fixed, col) not in placements and self.grid[fixed][col] is None:
                    raise PlayError("Tiles must be next to each other.")
        else:
            fixed = next(iter(cols))
            positions = sorted(r for r, _ in placements)
            for row in range(positions[0], positions[-1] + 1):
                if (row, fixed) not in placements and self.grid[row][fixed] is None:
                    raise PlayError("Tiles must be next to each other.")

        return orientation, fixed

    def is_connected(self, placements: dict[tuple[int, int], Cell]) -> bool:
        if self.is_empty():
            return any(pos == CENTER_SQUARE for pos in placements)
        if not placements:
            return False

        combined = self.clone()
        combined.apply(placements)
        for row, col in placements:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = row + dr, col + dc
                if in_bounds(nr, nc) and self.grid[nr][nc] is not None:
                    return True
        return False

    # ----------------------------------------------------------------- scoring
    def _word_cells(self, combined: "Board", row: int, col: int, d_row: int, d_col: int) -> list[tuple[int, int]]:
        sr, sc = row, col
        while in_bounds(sr - d_row, sc - d_col) and combined.grid[sr - d_row][sc - d_col] is not None:
            sr -= d_row
            sc -= d_col
        cells: list[tuple[int, int]] = []
        while in_bounds(sr, sc) and combined.grid[sr][sc] is not None:
            cells.append((sr, sc))
            sr += d_row
            sc += d_col
        return cells

    def _score_word(self, combined: "Board", cells: list[tuple[int, int]], new_cells: set[tuple[int, int]]) -> int:
        total = 0
        word_multiplier = 1
        for row, col in cells:
            cell = combined.grid[row][col]
            assert cell is not None
            letter, blank = cell
            value = 0 if blank else LETTER_VALUES.get(letter, 0)
            if (row, col) in new_cells:
                premium = BOARD_PREMIUMS.get((row, col), "")
                if premium == "DL":
                    value *= 2
                elif premium == "TL":
                    value *= 3
                elif premium == "DW":
                    word_multiplier *= 2
                elif premium == "TW":
                    word_multiplier *= 3
            total += value
        return total * word_multiplier

    def score_play(
        self,
        placements: dict[tuple[int, int], Cell],
        lexicon,
        words_allowed: bool = True,
        *,
        bingo_bonus: bool = True,
        minimum_word_length: int = 0,
    ) -> PlayResult:
        if not placements:
            raise PlayError("Place at least one tile.")
        orientation, _fixed = self.check_shape(placements)

        combined = self.clone()
        combined.apply(placements)
        new_cells = set(placements)

        words: list[tuple[list[tuple[int, int]], str]] = []
        seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()

        def add_word(cells: list[tuple[int, int]]) -> None:
            if len(cells) < 2:
                return
            key = (cells[0], cells[-1])
            if key in seen:
                return
            seen.add(key)
            words.append((cells, "".join(combined.grid[r][c][0] for r, c in cells)))

        if len(placements) == 1:
            row, col = next(iter(placements))
            add_word(self._word_cells(combined, row, col, 0, 1))
            add_word(self._word_cells(combined, row, col, 1, 0))
        else:
            anchor = next(iter(placements))
            if orientation == "H":
                add_word(self._word_cells(combined, anchor[0], anchor[1], 0, 1))
            else:
                add_word(self._word_cells(combined, anchor[0], anchor[1], 1, 0))

        for row, col in placements:
            if orientation == "H":
                add_word(self._word_cells(combined, row, col, 1, 0))
            else:
                add_word(self._word_cells(combined, row, col, 0, 1))

        if not self.is_connected(placements):
            raise PlayError("The play must join the tiles already on the board.")

        if not words:
            raise PlayError("A play must make a word of at least two letters.")

        if minimum_word_length:
            for _cells, text in words:
                if len(text) < minimum_word_length:
                    raise PlayError(f"Words must be at least {minimum_word_length} letters.")

        if words_allowed and lexicon is not None:
            for _cells, text in words:
                if not lexicon.contains(text):
                    raise PlayError(f"{text} is not in {getattr(lexicon, 'label', 'CSW24')}.")

        total = 0
        detail: list[tuple[str, int]] = []
        for cells, text in words:
            value = self._score_word(combined, cells, new_cells)
            detail.append((text, value))
            total += value

        bingo = bingo_bonus and len(placements) == 7
        if bingo:
            total += BINGO_BONUS

        return PlayResult(score=total, words=detail, bingo=bingo, placements=dict(placements))
