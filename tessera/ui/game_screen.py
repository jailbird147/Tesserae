"""The board: board, rack, clock bar and action buttons."""

from __future__ import annotations

import time

import pygame

from ..board import Board, PlayError
from ..tiles import ALPHABET, BOARD_PREMIUMS, LETTER_VALUES
from . import theme
from .widgets import Button

CELL = 42
BOARD_ORIGIN = (40, 124)
BOARD_PX = CELL * 15

RACK_Y = 790
RACK_X = 83
RACK_TILE = 70
RACK_GAP = 9

PANEL_RECT = (710, 104, 870, 670)
RACK_RECT = (20, 780, 670, 114)

PLAYER_COLORS = [
    (236, 184, 84),
    (122, 196, 214),
    (196, 152, 232),
    (150, 206, 142),
]


class GameScreen:
    def __init__(self, app) -> None:
        self.app = app
        self.client = app.client
        self.board = Board()
        self.players: list[dict] = []
        self.state: dict | None = None
        self.viewer: int | None = None
        self.turn_key: tuple[int, int] | None = None
        self.pending: dict[tuple[int, int], tuple[str, bool, int]] = {}
        self.selected: int | None = None
        self.dragging: int | None = None
        self.drag_pos = (0, 0)
        self.exchange_mode = False
        self.exchange_selection: set[int] = set()
        self.locked = False
        self.modal: str | None = None
        self.blank_square: tuple[int, int] | None = None
        self.hints: list[dict] = []
        self.hint_rects: list[pygame.Rect] = []
        self.yield_buttons: list[Button] = []
        self.rack_order: list[int] = []
        self._last_letters: list[str] = []
        self.last_cells: set[tuple[int, int]] = set()
        self.allow_hints = True
        self.bingo_bonus = True
        self.minimum_word_length = 0
        self.watchers = 0
        self.tournament_mode = False
        self.tournament: dict | None = None
        self.handles_errors = True
        self.remaining_at = 0.0
        self.snapshot_at = 0.0
        self.message = ""
        self.message_kind = "info"
        self._build_buttons()
        self.lexicon = None
        self.lexicon_label = "CSW24"
        self._load_lexicon_for_snapshot()

    def enter(self) -> None:
        pass

    # ------------------------------------------------------------------ layout
    def _build_buttons(self) -> None:
        self.buttons = {
            "play": Button((710, 780, 230, 52), "Play", self.do_play, style="primary", size=21),
            "recall": Button((952, 780, 230, 52), "Recall", self.do_recall),
            "hint": Button((1194, 780, 262, 52), "Hint", self.do_hint),
            "exchange": Button((710, 840, 230, 46), "Exchange", self.toggle_exchange),
            "pass": Button((952, 840, 160, 46), "Pass", self.do_pass),
            "yield": Button((1124, 840, 160, 46), "Yield", self.ask_yield, style="danger"),
            "recycle": Button((1296, 840, 160, 46), "Recycle ?", self.do_recycle),
        }

    # ------------------------------------------------------------------- state
    @property
    def snapshot(self) -> dict | None:
        return self.client.snapshot if self.client else None

    def _raw_rack(self) -> list[str]:
        if not self.players or self.viewer is None or self.viewer >= len(self.players):
            return []
        return list(self.players[self.viewer].get("rack", []))

    def _rack(self) -> list[str]:
        raw = self._raw_rack()
        if len(self.rack_order) != len(raw):
            self.rack_order = list(range(len(raw)))
        return [raw[index] for index in self.rack_order]

    def _sync_rack_order(self) -> None:
        raw = self._raw_rack()
        if sorted(raw) != sorted(self._last_letters) or len(raw) != len(self._last_letters):
            self.rack_order = list(range(len(raw)))
            self._last_letters = raw

    def _my_turn(self) -> bool:
        return (
            self.state is not None
            and self.client is not None
            and self.client.connected
            and not self.locked
            and self.state.get("current") == self.viewer
            and not self.state.get("game_over")
        )

    def _load_lexicon_for_snapshot(self) -> None:
        from ..lexicon import load_lexicon
        snapshot = self.snapshot
        settings = (snapshot or {}).get("settings", {})
        name = settings.get("lexicon") or "csw"
        self.lexicon_label = settings.get("lexicon_label") or "CSW24"
        if self.lexicon is None or self.lexicon.name != name:
            self.lexicon = load_lexicon(name)

    def _sync(self) -> None:
        snapshot = self.snapshot
        if not snapshot or not snapshot.get("state"):
            return
        self._load_lexicon_for_snapshot()
        state = snapshot["state"]
        self.state = state
        self.viewer = snapshot.get("viewer")
        self.players = state["players"]
        settings = snapshot.get("settings", {})
        self.allow_hints = bool(settings.get("allow_hints", True))
        self.bingo_bonus = bool(settings.get("bingo_bonus", True))
        self.minimum_word_length = int(settings.get("minimum_word_length", 0))
        self.watchers = len(snapshot.get("observers", []))
        self.tournament = snapshot.get("tournament")
        self.last_cells = {tuple(cell) for cell in state.get("last_cells", [])}
        self._sync_rack_order()

        board_cells = [
            (r, c, cell[0], bool(cell[1]))
            for r, row in enumerate(state["board"])
            for c, cell in enumerate(row)
            if cell
        ]
        self.board = Board()
        self.board.import_cells(board_cells)

        key = (state["turn"], state["current"] if state["current"] is not None else -1)
        if self.turn_key is None:
            self.turn_key = key
        elif key != self.turn_key:
            self.turn_key = key
            self.pending.clear()
            self.selected = None
            self.exchange_mode = False
            self.exchange_selection.clear()
            self.hints = []
            self.locked = False

        self.remaining_at = snapshot.get("turn_remaining", state.get("turn_seconds", 120))
        self.snapshot_at = time.monotonic()

        if state.get("game_over") and not self.tournament_mode and self.modal != "results":
            from .app import ResultsScreen
            self.app.switch(ResultsScreen(self.app))

        for hint in self.client.drain_hints() if self.client else []:
            self.hints = hint.get("moves", [])
            if not self.hints:
                self.app.toast("No hints available.", "info")

    def update(self, dt: float) -> None:
        if self.client is None or not self.client.connected:
            return
        self._sync()
        for error in self.client.drain_errors() if self.client else []:
            self.app.toast(error, "error")
            self.locked = False

    # ---------------------------------------------------------------- helpers
    def _board_pos(self, pos) -> tuple[int, int] | None:
        x, y = pos
        bx, by = BOARD_ORIGIN
        if bx <= x < bx + BOARD_PX and by <= y < by + BOARD_PX:
            return ((y - by) // CELL, (x - bx) // CELL)
        return None

    def _cell_rect(self, row: int, col: int) -> pygame.Rect:
        return pygame.Rect(BOARD_ORIGIN[0] + col * CELL, BOARD_ORIGIN[1] + row * CELL, CELL, CELL)

    def _rack_slot(self, index: int) -> pygame.Rect:
        return pygame.Rect(RACK_X + index * (RACK_TILE + RACK_GAP), RACK_Y, RACK_TILE, RACK_TILE)

    def _rack_hit(self, pos) -> int | None:
        for index in range(len(self._rack())):
            if self._rack_slot(index).collidepoint(pos):
                return index
        return None

    def _used_slots(self) -> set[int]:
        return {index for _letter, _blank, index in self.pending.values()}

    def _place(self, row: int, col: int, rack_index: int) -> None:
        if self.board.grid[row][col] is not None or (row, col) in self.pending:
            return
        if not self._my_turn():
            self.app.toast("Wait for your turn.", "info")
            return
        rack = self._rack()
        if rack_index >= len(rack) or rack_index in self._used_slots():
            return
        letter = rack[rack_index]
        if letter == "?":
            self.blank_square = (row, col)
            self.modal = "blank"
            self.selected = rack_index
            return
        self.pending[(row, col)] = (letter, False, rack_index)
        self.selected = None
        self.message = ""

    def _place_blank(self, letter: str) -> None:
        if self.blank_square is None or self.selected is None:
            self.modal = None
            return
        row, col = self.blank_square
        self.pending[(row, col)] = (letter, True, self.selected)
        self.modal = None
        self.blank_square = None
        self.selected = None
        self.message = ""

    def _recall(self) -> None:
        self.pending.clear()
        self.selected = None
        self.message = ""

    def _preview(self):
        if not self.pending:
            return None, "Place tiles on the board."
        placements = {(row, col): (letter, blank) for (row, col), (letter, blank, _index) in self.pending.items()}
        try:
            result = self.board.score_play(
                placements, self.lexicon,
                bingo_bonus=self.bingo_bonus,
                minimum_word_length=self.minimum_word_length,
            )
        except PlayError as exc:
            return None, str(exc)
        return result, ""

    # ----------------------------------------------------------------- actions
    def do_play(self) -> None:
        if not self._my_turn():
            return
        result, problem = self._preview()
        if result is None:
            self.app.toast(problem, "error")
            return
        cells = [
            (row, col, letter, blank)
            for (row, col), (letter, blank, _index) in self.pending.items()
        ]
        self.client.play(cells)
        self.locked = True
        self.message = "Play sent."
        self.message_kind = "success"

    def _rack_drop_index(self, pos) -> int | None:
        """Which rack slot a dropped tile lands in, or None if outside the rack."""
        if not pygame.Rect(RACK_RECT).collidepoint(pos):
            return None
        count = len(self._rack())
        if count < 2:
            return None
        slot = int(round((pos[0] - RACK_X) / (RACK_TILE + RACK_GAP)))
        return max(0, min(count - 1, slot))

    def move_rack_tile(self, source: int, target: int) -> None:
        """Slide one tile to another slot, keeping pending tiles attached to
        their letters."""
        order = self.rack_order
        if source == target or not (0 <= source < len(order)) or not (0 <= target < len(order)):
            return
        order.insert(target, order.pop(source))

        def remap(index: int | None) -> int | None:
            if index is None:
                return None
            if index == source:
                return target
            if source < target and source < index <= target:
                return index - 1
            if target < source and target <= index < source:
                return index + 1
            return index

        self.pending = {
            pos: (letter, blank, remap(index))  # type: ignore[misc]
            for pos, (letter, blank, index) in self.pending.items()
        }
        self.selected = remap(self.selected)
        self.exchange_selection = {index for index in (remap(i) for i in self.exchange_selection) if index is not None}

    def do_recall(self) -> None:
        self._recall()

    def do_hint(self) -> None:
        if not self._my_turn():
            return
        self.client.ask_hint()
        self.app.toast("Thinking...", "info")

    def toggle_exchange(self) -> None:
        if not self._my_turn():
            return
        if not self.exchange_mode:
            if self.state and self.state.get("bag", 0) < 7:
                self.app.toast("You cannot exchange with fewer than seven tiles in the bag.", "error")
                return
            self.exchange_mode = True
            self.exchange_selection.clear()
            self.pending.clear()
            return
        if not self.exchange_selection:
            self.app.toast("Pick the tiles you want to swap.", "info")
            return
        letters = [self._rack()[index] for index in sorted(self.exchange_selection)]
        self.client.exchange(letters)
        self.locked = True
        self.exchange_mode = False
        self.exchange_selection.clear()

    def do_pass(self) -> None:
        if not self._my_turn():
            return
        self.client.pass_turn()
        self.locked = True

    def do_recycle(self) -> None:
        if not self._my_turn():
            return
        self.client.recycle_blanks()
        self.locked = True

    def ask_yield(self) -> None:
        if not self._my_turn():
            return
        panel = pygame.Rect(380, 300, 460, 240)
        self.yield_buttons = [
            Button((panel.x + 60, panel.y + 150, 150, 50), "Yield", self.do_yield, style="danger", size=19),
            Button((panel.x + 250, panel.y + 150, 150, 50), "Keep playing", self._close_yield, size=19),
        ]
        self.modal = "yield"

    def do_yield(self) -> None:
        self.client.yield_game()
        self.modal = None
        self.locked = True

    def map_cells_to_rack(self, cells):
        """Match a suggested play's letters to rack slots, using a blank when
        the exact letter is not held. Returns None if the rack cannot cover it."""
        mapping = []
        used: set[int] = set()
        rack = self._rack()
        for row, col, letter, blank in cells:
            choice = None
            for rack_index, tile in enumerate(rack):
                if rack_index in used:
                    continue
                if blank and tile == "?":
                    choice = rack_index
                    break
                if not blank and tile == letter:
                    choice = rack_index
                    break
            if choice is None:
                for rack_index, tile in enumerate(rack):
                    if rack_index in used:
                        continue
                    if tile == "?":
                        choice = rack_index
                        blank = True
                        break
            if choice is None:
                return None
            used.add(choice)
            mapping.append((row, col, letter, bool(blank), choice))
        return mapping

    def apply_hint(self, hint: dict) -> None:
        if not self._my_turn():
            return
        mapping = self.map_cells_to_rack(hint.get("cells", []))
        if mapping is None:
            self.app.toast("That hint does not match your rack.", "error")
            self.pending.clear()
            return
        self.pending.clear()
        for row, col, letter, blank, choice in mapping:
            self.pending[(row, col)] = (letter, blank, choice)
        self.hints = []

    # ------------------------------------------------------------------ events
    def handle_event(self, event) -> None:
        if self.modal == "blank":
            self._handle_blank_modal(event)
            return
        if self.modal == "yield":
            self._handle_yield_modal(event)
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.exchange_mode:
                    self.exchange_mode = False
                    self.exchange_selection.clear()
                elif self.pending:
                    self._recall()
                else:
                    from .settings_screen import SettingsScreen
                    self.app.switch(SettingsScreen(self.app, back_target=self))
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.pending:
                    self.do_play()
            elif event.key == pygame.K_BACKSPACE:
                self._recall()
            return

        for button in self.buttons.values():
            if button.handle_event(event):
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = self._rack_hit(event.pos)
            if hit is not None:
                self.dragging = hit
                self.drag_pos = event.pos
                if self.exchange_mode:
                    if hit in self.exchange_selection:
                        self.exchange_selection.remove(hit)
                    else:
                        self.exchange_selection.add(hit)
                else:
                    self.selected = None if self.selected == hit else hit
                return

            pos = self._board_pos(event.pos)
            if pos is not None:
                row, col = pos
                if (row, col) in self.pending:
                    self.pending.pop((row, col))
                    self.message = ""
                elif self.selected is not None:
                    self._place(row, col, self.selected)
                return

            # Clicking a hint card plays it.
            for index, hint_rect in enumerate(getattr(self, "hint_rects", [])):
                if hint_rect.collidepoint(event.pos) and index < len(self.hints):
                    self.apply_hint(self.hints[index])
                    return

        elif event.type == pygame.MOUSEMOTION and self.dragging is not None:
            self.drag_pos = event.pos

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging is not None:
                index = self.dragging
                self.dragging = None
                pos = self._board_pos(event.pos)
                if pos is not None and not self.exchange_mode:
                    self._place(pos[0], pos[1], index)
                elif not self.exchange_mode:
                    drop = self._rack_drop_index(event.pos)
                    if drop is not None:
                        self.move_rack_tile(index, drop)
            self.hint_rects = getattr(self, "hint_rects", [])

    def _handle_blank_modal(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.modal = None
                self.blank_square = None
                return
            if event.unicode and event.unicode.upper() in ALPHABET:
                self._place_blank(event.unicode.upper())
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for letter, rect in self._blank_rects():
                if rect.collidepoint(event.pos):
                    self._place_blank(letter)
                    return
            if self._blank_panel().collidepoint(event.pos) is False:
                self.modal = None
                self.blank_square = None

    def _handle_yield_modal(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.modal = None
            return
        for button in self.yield_buttons:
            if button.handle_event(event):
                return

    def _blank_panel(self) -> pygame.Rect:
        return pygame.Rect(370, 210, 500, 430)

    def _blank_rects(self):
        panel = self._blank_panel()
        rects = []
        size = 56
        gap = 8
        per_row = 7
        for index, letter in enumerate(ALPHABET):
            row, col = divmod(index, per_row)
            x = panel.x + 24 + col * (size + gap)
            y = panel.y + 96 + row * (size + gap)
            rects.append((letter, pygame.Rect(x, y, size, size)))
        return rects

    # -------------------------------------------------------------------- draw
    def draw(self, surface) -> None:
        surface.fill(theme.BG_DARK)
        theme.vgradient(surface, pygame.Rect(0, 0, surface.get_width(), surface.get_height()),
                        (24, 62, 52), theme.BG_DARK)
        self._draw_top(surface)
        self._draw_board(surface)
        self._draw_panel(surface)
        self._draw_rack(surface)
        self._draw_buttons(surface)
        if self.modal == "blank":
            self._draw_blank_modal(surface)
        elif self.modal == "yield":
            self._draw_yield_modal(surface)
        if self.dragging is not None:
            rect = pygame.Rect(0, 0, RACK_TILE, RACK_TILE)
            rect.center = self.drag_pos
            rack = self._rack()
            if self.dragging < len(rack):
                theme.draw_tile(surface, rect, rack[self.dragging], None if rack[self.dragging] == "?" else LETTER_VALUES.get(rack[self.dragging], 0))

    def _draw_top(self, surface) -> None:
        bar = pygame.Rect(0, 0, surface.get_width(), 104)
        theme.vgradient(surface, bar, (18, 72, 75), (11, 50, 53))
        pygame.draw.line(surface, theme.LINE, (0, bar.bottom - 1), (bar.right, bar.bottom - 1))

        players = self.players or []
        if not players:
            return
        count = len(players)
        margin = 22
        gap = 12
        # Keep the cards from stretching absurdly wide with only two players.
        card_w = min(620.0, (surface.get_width() - margin * 2 - gap * (count - 1)) / count)
        total = card_w * count + gap * (count - 1)
        margin = int((surface.get_width() - total) / 2)
        now = time.monotonic()
        for index, player in enumerate(players):
            rect = pygame.Rect(int(margin + index * (card_w + gap)), 12, int(card_w), 78)
            active = self.state and self.state.get("current") == index and not self.state.get("game_over")
            color = PLAYER_COLORS[index % len(PLAYER_COLORS)]
            theme.rounded_rect(surface, rect, theme.PANEL_HI if active else theme.PANEL, 12)
            if active:
                pygame.draw.rect(surface, color, rect, width=2, border_radius=12)

            dot = color if player.get("connected", True) else theme.MUTED
            pygame.draw.circle(surface, dot, (rect.x + 20, rect.y + 26), 6)
            name = player["name"]
            theme.text(surface, name, 19, theme.TEXT, (rect.x + 34, rect.y + 14), bold=True)
            if index == self.viewer:
                tag = pygame.Rect(rect.x + 34 + theme.font(19, True).size(name)[0] + 10, rect.y + 17, 34, 20)
                theme.rounded_rect(surface, tag, theme.ACCENT, 6)
                theme.text(surface, "YOU", 11, (38, 34, 24), tag.center, "center", bold=True)
            theme.text(surface, str(player["score"]), 30, theme.ACCENT, (rect.right - 18, rect.y + 14), "topright", bold=True)
            info = f"{player['tiles_left']} tiles"
            if player.get("is_bot"):
                from ..bot import level_info
                info = level_info(player.get("level", 3))["name"] + " · " + info
            if not player.get("connected", True):
                info = "away · " + info
            theme.text(surface, info, 14, theme.MUTED, (rect.x + 20, rect.y + 48))

            seconds = self.state.get("turn_seconds", 120) if self.state else 120
            remaining = seconds
            if active:
                elapsed = now - self.snapshot_at
                remaining = max(0.0, self.remaining_at - elapsed)

            # Last ten seconds: the clock flashes red so you cannot miss it.
            urgent = bool(active) and not self.state.get("game_over") and 0 < remaining <= 10.0
            flash_on = (now * 2.2) % 1.0 < 0.5
            clock = theme.format_clock(remaining)
            if urgent:
                clock_color = theme.DANGER if flash_on else theme.TEXT
            else:
                clock_color = theme.DANGER if remaining <= 15 else theme.TEXT
            theme.text(surface, clock, 19 if urgent else 18, clock_color,
                       (rect.right - 18, rect.y + 48), "topright", bold=True)
            if urgent and flash_on:
                pygame.draw.rect(surface, theme.DANGER, rect, width=2, border_radius=12)
            bar = pygame.Rect(rect.x + 12, rect.bottom - 9, rect.width - 24, 5)
            fraction = remaining / max(1, seconds)
            theme.draw_clock_bar(surface, bar, fraction, theme.DANGER if remaining <= 10 else color)

    def _draw_board(self, surface) -> None:
        frame = pygame.Rect(BOARD_ORIGIN[0] - 20, BOARD_ORIGIN[1] - 20, BOARD_PX + 40, BOARD_PX + 40)
        theme.rounded_rect(surface, frame.move(0, 4), (5, 30, 32), 12)
        theme.rounded_rect(surface, frame, theme.BOARD_WOOD, 12)
        pygame.draw.rect(surface, theme.BOARD_INNER, frame, width=1, border_radius=12)

        if self.app.settings.get("show_coordinates", True):
            for col in range(15):
                rect = self._cell_rect(0, col)
                theme.text(surface, chr(ord("A") + col), 12, theme.MUTED,
                           (rect.centerx, BOARD_ORIGIN[1] - 11), "center", bold=True)
            for row in range(15):
                rect = self._cell_rect(row, 0)
                theme.text(surface, str(row + 1), 11, theme.MUTED,
                           (BOARD_ORIGIN[0] - 11, rect.centery), "center", bold=True)

        for row in range(15):
            for col in range(15):
                rect = self._cell_rect(row, col)
                premium = BOARD_PREMIUMS.get((row, col), "")
                color = theme.PREMIUM_COLORS.get(premium, theme.SQUARE)
                pygame.draw.rect(surface, color, rect)
                pygame.draw.rect(surface, theme.GRID, rect, width=1)
                if premium and self.board.grid[row][col] is None and (row, col) not in self.pending:
                    theme.text(surface, premium, 10, theme.PREMIUM_TEXT[premium], rect.center, "center", bold=True)
                if (row, col) == (7, 7) and self.board.grid[row][col] is None and (row, col) not in self.pending:
                    pygame.draw.circle(surface, theme.ACCENT, rect.center, 5)

        for row in range(15):
            for col in range(15):
                cell = self.board.grid[row][col]
                if cell is None:
                    continue
                letter, blank = cell
                rect = self._cell_rect(row, col).inflate(-2, -2)
                theme.draw_tile(surface, rect, letter, None if blank else LETTER_VALUES.get(letter, 0), blank=blank, small=True)

        if self.app.settings.get("highlight_last_move", True) and self.last_cells:
            for row, col in self.last_cells:
                if (row, col) in self.pending:
                    continue
                rect = self._cell_rect(row, col).inflate(2, 2)
                pygame.draw.rect(surface, theme.ACCENT, rect, width=2, border_radius=4)

        for (row, col), (letter, blank, _index) in self.pending.items():
            rect = self._cell_rect(row, col).inflate(-2, -2)
            theme.draw_tile(surface, rect, letter, None if blank else LETTER_VALUES.get(letter, 0),
                            blank=blank, small=True, highlight=theme.ACCENT)

        # Preview score chip next to the board.
        result, problem = self._preview()
        if result is not None:
            chip = pygame.Rect(BOARD_ORIGIN[0] + BOARD_PX - 210, BOARD_ORIGIN[1] + BOARD_PX - 44, 200, 36)
            theme.rounded_rect(surface, chip, theme.PANEL, 10)
            pygame.draw.rect(surface, theme.ACCENT, chip, width=1, border_radius=10)
            label = f"{result.score} points"
            if result.bingo:
                label += " · BINGO!"
            theme.text(surface, label, 19, theme.ACCENT, chip.center, "center", bold=True)

    def _draw_panel(self, surface) -> None:
        panel = pygame.Rect(*PANEL_RECT)
        theme.panel(surface, panel)
        if not self.state:
            theme.text(surface, "Connecting...", 20, theme.MUTED, (panel.x + 24, panel.y + 24))
            return

        heading = f"Turn {self.state['turn']}"
        if self.tournament:
            round_number = self.tournament.get("round", 1)
            heading = f"Round {round_number} · Turn {self.state['turn']}"
        theme.heading(surface, heading, 24, (panel.x + 24, panel.y + 18))
        theme.text(surface, f"{self.lexicon_label} · {self.state['bag']} in the bag", 15, theme.MUTED,
                   (panel.right - 24, panel.y + 27), "topright")
        if self.tournament:
            pair = self.tournament.get("current") or {}
            theme.text(surface, f"{self.tournament.get('name', '')} · {pair.get('a', '')} vs {pair.get('b', '')}",
                       13, theme.ACCENT, (panel.x + 26, panel.y + 50))

        y = panel.y + 72
        if self.state.get("game_over"):
            theme.text(surface, self.state.get("result", ""), 19, theme.ACCENT, (panel.x + 24, y), bold=True)
        elif self.viewer is None:
            label = "Spectating" + (f" - {self.watchers} watching" if self.watchers else "")
            theme.text(surface, label, 20, theme.SUCCESS, (panel.x + 24, y), bold=True)
        elif self._my_turn():
            theme.text(surface, "Your move.", 20, theme.SUCCESS, (panel.x + 24, y), bold=True)
        else:
            current = self.state.get("current")
            name = self.players[current]["name"] if current is not None and current < len(self.players) else "someone"
            theme.text(surface, f"{name} is thinking...", 20, theme.MUTED, (panel.x + 24, y))

        if self.pending:
            result, problem = self._preview()
            if problem:
                theme.text(surface, problem, 15, theme.DANGER, (panel.x + 24, y + 28))
            elif result:
                words = ", ".join(word for word, _ in result.words)
                theme.text(surface, f"{words}  ({result.score})", 15, theme.MUTED, (panel.x + 24, y + 28))
        elif self.message:
            color = theme.DANGER if self.message_kind == "error" else theme.MUTED
            theme.text(surface, self.message, 15, color, (panel.x + 24, y + 28))

        # Move log
        log_rect = pygame.Rect(panel.x + 20, panel.y + 120, panel.w - 40, 250)
        pygame.draw.line(surface, theme.LINE, (log_rect.x, log_rect.y - 10), (log_rect.right, log_rect.y - 10))
        entries = self.state.get("history", [])[-8:]
        for index, entry in enumerate(reversed(entries)):
            row_y = log_rect.bottom - 26 - index * 29
            if row_y < log_rect.y:
                break
            color = PLAYER_COLORS[entry["seat"] % len(PLAYER_COLORS)]
            pygame.draw.circle(surface, color, (log_rect.x + 6, row_y + 9), 5)
            theme.text(surface, entry["name"], 15, theme.MUTED, (log_rect.x + 18, row_y), bold=True)
            theme.text(surface, entry["detail"], 15, theme.TEXT, (log_rect.x + 170, row_y))
            if entry["score"]:
                theme.text(surface, f"+{entry['score']}", 15, theme.ACCENT,
                           (log_rect.right - 6, row_y), "topright", bold=True)

        # Hints
        self.hint_rects = []
        hint_y = panel.y + 370
        if self.hints:
            theme.text(surface, "Engine suggestions - click to place", 15, theme.MUTED, (panel.x + 24, hint_y))
            hint_y += 20
            for index, hint in enumerate(self.hints[:3]):
                rect = pygame.Rect(panel.x + 20, hint_y + index * 45, panel.w - 40, 40)
                theme.rounded_rect(surface, rect, theme.PANEL_SOFT, 9)
                theme.text(surface, hint.get("word", ""), 17, theme.TEXT, (rect.x + 14, rect.centery), "midleft", bold=True)
                theme.text(surface, str(hint.get("score", "")), 17, theme.ACCENT, (rect.right - 14, rect.centery), "midright", bold=True)
                self.hint_rects.append(rect)

        # Rules reference at the bottom of the panel.
        foot = pygame.Rect(panel.x + 20, panel.bottom - 132, panel.w - 40, 110)
        theme.rounded_rect(surface, foot, theme.PANEL, 10)
        theme.text(surface, "Rules quick reference", 14, theme.MUTED, (foot.x + 14, foot.y + 10), bold=True)
        theme.text(surface, "Bingo: all 7 tiles  +50", 13, theme.TEXT, (foot.x + 14, foot.y + 34))
        theme.text(surface, f"Words checked against {self.lexicon_label} ({self.state.get('word_count', 0):,})", 13, theme.TEXT, (foot.x + 14, foot.y + 54))
        if self.state.get("allow_blank_recycle"):
            theme.text(surface, "Blank recycle: once per player per game", 13, theme.TEXT, (foot.x + 14, foot.y + 74))

    def _draw_rack(self, surface) -> None:
        rack_bg = pygame.Rect(*RACK_RECT)
        theme.rounded_rect(surface, rack_bg.move(0, 4), (5, 30, 32), 12)
        theme.rounded_rect(surface, rack_bg, theme.PANEL, 12)
        pygame.draw.rect(surface, theme.LINE, rack_bg, width=1, border_radius=12)
        theme.text(surface, "SPECTATING" if self.viewer is None else "RACK", 11, theme.MUTED,
                   (rack_bg.x + 16, rack_bg.y + 9), bold=True)

        if self.viewer is None:
            theme.text(surface, "Spectating", 22, theme.TEXT, rack_bg.center, "center", bold=True)
            watchers = f"{self.watchers} watching" if self.watchers else ""
            if watchers:
                theme.text(surface, watchers, 13, theme.MUTED, (rack_bg.centerx, rack_bg.y + 92), "center")
            return

        rack = self._rack()
        used = self._used_slots()
        for index in range(7):
            slot = self._rack_slot(index)
            if index >= len(rack):
                pygame.draw.rect(surface, (86, 64, 46), slot, width=2, border_radius=8)
                continue
            letter = rack[index]
            if index in used:
                pygame.draw.rect(surface, (86, 64, 46), slot, width=1, border_radius=8)
                continue
            if self.dragging == index:
                continue
            selected = self.selected == index or index in self.exchange_selection
            highlight = None
            if self.exchange_mode and index in self.exchange_selection:
                highlight = theme.DANGER
            elif selected:
                highlight = theme.ACCENT
            theme.draw_tile(
                surface, slot, letter,
                None if letter == "?" else LETTER_VALUES.get(letter, 0),
                blank=(letter == "?"), highlight=highlight
            )

        if self.exchange_mode:
            theme.text(surface, "Pick tiles to swap, then press Exchange again", 11, theme.ACCENT,
                       (rack_bg.x + 74, rack_bg.y + 9), bold=True)
        elif len(rack) > 1:
            theme.text(surface, "Drag tiles to rearrange them", 11, theme.MUTED,
                       (rack_bg.centerx, rack_bg.y + 96), "center")

    def _draw_buttons(self, surface) -> None:
        if not self.state:
            return
        watching = self.viewer is None
        my_turn = self._my_turn() and not watching
        bag = self.state.get("bag", 0)
        can_exchange = my_turn and (self.exchange_mode or bag >= 7)
        self.buttons["play"].enabled = my_turn and bool(self.pending)
        self.buttons["recall"].enabled = bool(self.pending) and not watching
        self.buttons["hint"].enabled = my_turn and self.allow_hints
        self.buttons["exchange"].enabled = can_exchange
        self.buttons["pass"].enabled = my_turn
        self.buttons["yield"].enabled = my_turn
        recycle_ok = self.snapshot.get("can_recycle_blanks", False) if self.snapshot else False
        self.buttons["recycle"].enabled = my_turn and recycle_ok
        self.buttons["exchange"].label = "Confirm swap" if self.exchange_mode else "Exchange"
        for button in self.buttons.values():
            button.draw(surface)

    def _draw_blank_modal(self, surface) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))
        panel = self._blank_panel()
        theme.panel(surface, panel, theme.PANEL_HI, radius=16)
        theme.text(surface, "Blank tile", 24, theme.TEXT, (panel.x + 24, panel.y + 20), bold=True)
        theme.text(surface, "Choose the letter it stands for.", 15, theme.MUTED, (panel.x + 24, panel.y + 54))
        for letter, rect in self._blank_rects():
            hover = rect.collidepoint(pygame.mouse.get_pos())
            theme.draw_tile(surface, rect, letter, None, highlight=theme.ACCENT if hover else None, small=True)
        theme.text(surface, "Esc cancels", 13, theme.MUTED, (panel.x + 24, panel.bottom - 28))

    def _draw_yield_modal(self, surface) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))
        panel = pygame.Rect(380, 300, 460, 240)
        theme.panel(surface, panel, theme.PANEL_HI, radius=16)
        theme.text(surface, "Yield the match?", 26, theme.TEXT, (panel.centerx, panel.y + 40), "center", bold=True)
        theme.text(surface, "Your opponent wins. This cannot be undone.", 16, theme.MUTED, (panel.centerx, panel.y + 80), "center")
        for button in self.yield_buttons:
            button.draw(surface)

    def _close_yield(self) -> None:
        self.modal = None
