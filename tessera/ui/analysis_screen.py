"""Post-game analysis screen: Quackle's verdict on your moves."""

from __future__ import annotations

import pygame

from . import theme
from .widgets import Button

VERDICT_COLORS = {
    "Best": theme.SUCCESS,
    "Good": theme.TEXT,
    "Inaccuracy": (226, 196, 108),
    "Mistake": (226, 148, 96),
    "Blunder": theme.DANGER,
    "Unknown": theme.MUTED,
}

COLUMNS = [
    ("Turn", 70),
    ("You played", 260),
    ("Pts", 60),
    ("Best play", 250),
    ("Pts", 60),
    ("Lost", 80),
    ("Verdict", 130),
    ("", 44),
]

VERDICT_HELP = {
    "Best": "Quackle's top choice for this position, or within 1 equity of it.",
    "Good": "Within 4 equity of the best play. A sound move.",
    "Inaccuracy": "4 to 10 equity worse than the best play. Playable, but it gives ground.",
    "Mistake": "10 to 18 equity worse than the best play. This one loses real value.",
    "Blunder": "18 or more equity worse. A serious error.",
    "Unknown": "Quackle could not score this position.",
}

SUMMARY_HELP = (
    "Equity is Quackle's value for a play: the points you score, plus what your "
    "leftover tiles are worth, plus how good the board position is.\n"
    "Losing about 4 or less per move is strong club play. The rating band is a "
    "rough estimate from that average, not an official rating."
)


class AnalysisScreen:
    def __init__(self, app, back_target=None) -> None:
        self.app = app
        self.back_target = back_target
        self.scroll = 0
        self.back = Button((240, 800, 170, 48), "Back", self.go_back)
        self.visible_rows = 11
        self.row_height = 30
        self.help_icons: list[tuple[pygame.Rect, str]] = []
        self._hover_pos: tuple[int, int] | None = None  # test hook

    def enter(self) -> None:
        if self.app.client and self.app.client.analysis is None:
            self.app.client.ask_analysis()

    def go_back(self) -> None:
        if self.back_target is not None:
            self.app.switch(self.back_target)
        else:
            from .app import ResultsScreen, MenuScreen
            snapshot = self.app.client.snapshot if self.app.client else None
            if snapshot and snapshot.get("state", {}).get("game_over"):
                self.app.switch(ResultsScreen(self.app))
            else:
                self.app.switch(MenuScreen(self.app))

    # ---------------------------------------------------------------- events
    def handle_event(self, event) -> None:
        if self.back.handle_event(event):
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.go_back()
            elif event.key == pygame.K_DOWN:
                self.scroll += 1
            elif event.key == pygame.K_UP:
                self.scroll = max(0, self.scroll - 1)
            elif event.key == pygame.K_PAGEDOWN:
                self.scroll += self.visible_rows
            elif event.key == pygame.K_PAGEUP:
                self.scroll = max(0, self.scroll - self.visible_rows)
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y)

    def update(self, dt: float) -> None:
        analysis = self.app.client.analysis if self.app.client else None
        if analysis and analysis.get("phase") == "done":
            rows = analysis["data"]["moves"]
            self.scroll = max(0, min(self.scroll, max(0, len(rows) - self.visible_rows)))

    # ------------------------------------------------------------------ draw
    def draw(self, surface) -> None:
        self.help_icons = []
        surface.fill(theme.BG_DARK)
        theme.vgradient(surface, pygame.Rect(0, 0, *surface.get_size()), (18, 72, 75), theme.BG_DARK)
        theme.heading(surface, "Game analysis", 46, (240, 36))
        theme.text(surface, "Quackle equity: points, leave value and board position", 18, theme.MUTED, (242, 92))

        analysis = self.app.client.analysis if self.app.client else None
        if analysis is None:
            theme.text(surface, "Starting analysis...", 22, theme.TEXT, (240, 180))
            self.back.draw(surface)
            return

        phase = analysis.get("phase")
        if phase == "error":
            theme.text(surface, analysis.get("message", "Analysis failed."), 20, theme.DANGER, (240, 180))
            self.back.draw(surface)
            return

        if phase in ("starting", "progress"):
            done = analysis.get("done", 0)
            total = max(1, analysis.get("total", 1))
            theme.text(surface, f"Analysing move {done} of {total}...", 24, theme.TEXT, (240, 180), bold=True)
            bar = pygame.Rect(240, 220, 800, 12)
            theme.rounded_rect(surface, bar, theme.PANEL, 6)
            filled = pygame.Rect(bar.x, bar.y, int(bar.width * done / total), bar.height)
            theme.rounded_rect(surface, filled, theme.ACCENT, 6)
            theme.text(surface, "Quackle is scoring every position you played.", 16, theme.MUTED, (240, 252))
            self._draw_summary(surface, None)
            self.back.draw(surface)
            self._draw_tooltip(surface)
            return

        data = analysis.get("data") or {}
        rows = data.get("moves", [])
        summary = data.get("summary", {})
        self._draw_summary(surface, summary)
        self._draw_table(surface, rows)
        self.back.draw(surface)
        self._draw_tooltip(surface)

    # ------------------------------------------------------------------ help
    def _mouse_pos(self):
        return self._hover_pos if self._hover_pos is not None else pygame.mouse.get_pos()

    def _help_icon(self, surface, center, text) -> None:
        mouse = self._mouse_pos()
        hot = abs(mouse[0] - center[0]) <= 10 and abs(mouse[1] - center[1]) <= 10
        color = theme.ACCENT if hot else theme.MUTED
        pygame.draw.circle(surface, (18, 72, 75), center, 9)
        pygame.draw.circle(surface, color, center, 9, width=1)
        theme.text(surface, "?", 11, color, center, "center", bold=True)
        self.help_icons.append((pygame.Rect(center[0] - 11, center[1] - 11, 22, 22), text))

    def _row_help(self, row) -> str:
        verdict = row.get("verdict", "Unknown")
        best = row.get("best") or ""
        played = row.get("played") or ""
        lines = [f"{verdict}: {VERDICT_HELP.get(verdict, '')}"]

        if verdict == "Best":
            lines.append(
                f"You played {played} for {row.get('played_score', '?')} points."
                if played else "No better move was available."
            )
            return "\n".join(lines)

        if row.get("loss") is not None:
            lines.append(f"You gave up {row['loss']:.1f} equity compared with Quackle's choice.")
        if best and best != played:
            equity = row.get("best_equity")
            lines.append(
                f"Better: {best} for {row.get('best_score', '?')} points"
                + (f" ({equity:.1f} equity)." if equity is not None else ".")
            )
        if played:
            equity = row.get("played_equity")
            lines.append(
                f"You played: {played} for {row.get('played_score', '?')} points"
                + (f" ({equity:.1f} equity)." if equity is not None else ".")
            )
        return "\n".join(lines)

    def _draw_tooltip(self, surface) -> None:
        mouse = self._mouse_pos()
        for rect, text in self.help_icons:
            if rect.collidepoint(mouse):
                self._tooltip(surface, text, rect)
                return

    def _tooltip(self, surface, text: str, icon: pygame.Rect) -> None:
        width = 400
        lines: list[str] = []
        for paragraph in text.split("\n"):
            lines.extend(theme.wrap_text(paragraph, 13, width - 24))
        height = 20 + len(lines) * 18
        x = min(icon.centerx + 12, surface.get_width() - width - 12)
        x = max(12, x)
        y = icon.bottom + 8
        if y + height > surface.get_height() - 12:
            y = icon.top - height - 8
        rect = pygame.Rect(x, y, width, height)
        theme.rounded_rect(surface, rect.move(0, 3), (5, 30, 32), 8)
        theme.rounded_rect(surface, rect, theme.PANEL_HI, 8)
        pygame.draw.rect(surface, theme.ACCENT, rect, width=1, border_radius=8)
        for index, line in enumerate(lines):
            theme.text(surface, line, 13, theme.TEXT, (rect.x + 12, rect.y + 10 + index * 18))

    def _draw_summary(self, surface, summary) -> None:
        card = pygame.Rect(240, 130, 1120, 100)
        theme.panel(surface, card)
        if not summary:
            theme.text(surface, "Waiting for the first moves...", 17, theme.MUTED, (card.x + 24, card.centery), "midleft")
            return
        rating = summary.get("rating", "-")
        average = summary.get("average_loss", 0)
        theme.text(surface, "Estimated rating", 14, theme.MUTED, (card.x + 24, card.y + 20))
        theme.text(surface, str(rating), 26, theme.ACCENT, (card.x + 24, card.y + 40), bold=True)
        theme.text(surface, "Average equity lost", 14, theme.MUTED, (card.x + 240, card.y + 20))
        theme.text(surface, f"{average:.2f} per move", 22, theme.TEXT, (card.x + 240, card.y + 44), bold=True)
        self._help_icon(surface, (card.x + 420, card.y + 27), SUMMARY_HELP)
        items = [
            ("Best", summary.get("best", 0), VERDICT_COLORS["Best"]),
            ("Good", summary.get("good", 0), VERDICT_COLORS["Good"]),
            ("Inaccuracy", summary.get("inaccuracy", 0), VERDICT_COLORS["Inaccuracy"]),
            ("Mistake", summary.get("mistake", 0), VERDICT_COLORS["Mistake"]),
            ("Blunder", summary.get("blunder", 0), VERDICT_COLORS["Blunder"]),
        ]
        x = card.x + 520
        for label, value, color in items:
            theme.text(surface, str(value), 24, color, (x, card.y + 26), bold=True)
            theme.text(surface, label, 13, theme.MUTED, (x, card.y + 56))
            x += 120

    def _draw_table(self, surface, rows) -> None:
        table = pygame.Rect(240, 240, 1120, 520)
        theme.panel(surface, table, theme.PANEL, radius=12)
        header_y = table.y + 16
        x = table.x + 20
        for title, width in COLUMNS:
            theme.text(surface, title, 13, theme.MUTED, (x, header_y))
            x += width
        pygame.draw.line(surface, theme.LINE, (table.x + 16, header_y + 22), (table.right - 16, header_y + 22))

        if not rows:
            theme.text(surface, "No plays to analyse.", 18, theme.MUTED, (table.x + 24, header_y + 60))
            return

        max_rows = min(self.visible_rows, len(rows))
        start = max(0, min(self.scroll, len(rows) - max_rows))
        y = header_y + 32
        for offset, row in enumerate(rows[start:start + max_rows]):
            if ((start + offset) % 2) == 1:
                stripe = pygame.Rect(table.x + 10, y - 3, table.w - 20, self.row_height - 2)
                theme.rounded_rect(surface, stripe, (27, 62, 53), 6)
            color = VERDICT_COLORS.get(row.get("verdict", "Unknown"), theme.TEXT)
            x = table.x + 20
            values = [
                str(row.get("turn", "")),
                row.get("played", ""),
                str(row.get("played_score", "")),
                row.get("best", ""),
                str(row.get("best_score", "") if row.get("best_score") is not None else "-"),
                f"{row['loss']:.1f}" if row.get("loss") is not None else "-",
                row.get("verdict", ""),
            ]
            for (title, width), value in zip(COLUMNS, values):
                text_color = color if title == "Verdict" else theme.TEXT
                if title == "Best play":
                    text_color = theme.MUTED
                theme.text(surface, value, 15, text_color, (x, y))
                x += width
            self._help_icon(surface, (x + 14, y + 8), self._row_help(row))
            y += self.row_height

        if len(rows) > max_rows:
            hint = f"Showing {start + 1}-{start + max_rows} of {len(rows)} - scroll for more"
            theme.text(surface, hint, 13, theme.MUTED, (table.x + 20, table.bottom - 24))
