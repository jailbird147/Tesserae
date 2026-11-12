"""Tournament setup and the tournament board: roster, ladder and matches."""

from __future__ import annotations

import pygame

from ..tournament import FORMATS
from . import theme
from .widgets import Button, Stepper, TextInput, Toggle

TURN_CHOICES = [60, 90, 120, 180]


def _minutes(value: int) -> str:
    return f"{value // 60} min" if value % 60 == 0 else f"{value / 60:.1f} min"


class TournamentSetupScreen:
    def __init__(self, app) -> None:
        self.app = app
        settings = app.settings
        self.name_input = TextInput((470, 200, 440, 44), "Tournament name", 28,
                                    settings.get("tournament_name", "Tessera Cup"))
        self.format = Stepper((470, 264, 440, 40), "Format", ["swiss", "round_robin", "knockout"], 0,
                              format_value=lambda v: FORMATS[v]["label"])
        self.rounds = Stepper((470, 316, 440, 40), "Rounds (Swiss)", [2, 3, 4, 5], 1)
        self.capacity = Stepper((470, 368, 440, 40), "Places", [4, 6, 8, 12, 16], 2)
        self.turn_time = Stepper((470, 420, 440, 40), "Clock per turn", TURN_CHOICES,
                                 TURN_CHOICES.index(int(settings.get("turn_seconds", 120))) if int(settings.get("turn_seconds", 120)) in TURN_CHOICES else 2,
                                 format_value=_minutes)
        from .app import make_lexicon_stepper
        self.lexicon = make_lexicon_stepper((470, 472, 440, 40), settings.get("lexicon"))
        self.recycle = Toggle((470, 524, 440, 40), "One blank recycle per player",
                              bool(settings.get("allow_blank_recycle", True)))
        self.port_input = TextInput((470, 588, 200, 44), "Port", 5, str(settings.get("port", "5467")))
        self.create = Button((470, 660, 250, 54), "Create tournament", self.do_create, style="primary", size=20)
        self.back = Button((736, 660, 154, 54), "Back", self.go_back)
        self.error = ""

    def enter(self) -> None:
        pass

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.go_back()
            return
        for widget in [self.name_input, self.format, self.rounds, self.capacity, self.turn_time,
                       self.lexicon, self.recycle, self.port_input, self.create, self.back]:
            if widget.handle_event(event):
                return

    def update(self, dt: float) -> None:
        pass

    def go_back(self) -> None:
        from .app import MenuScreen
        self.app.switch(MenuScreen(self.app))

    def do_create(self) -> None:
        name = self.name_input.value.strip() or "Tessera Cup"
        try:
            port = int(self.port_input.value or "5467")
        except ValueError:
            self.error = "Port must be a number."
            return
        self.app.settings.update({
            "tournament_name": name,
            "turn_seconds": self.turn_time.value,
            "lexicon": self.lexicon.value,
            "allow_blank_recycle": self.recycle.value,
            "port": str(port),
        })
        from .app import save_settings
        save_settings(self.app.settings)
        try:
            self.app.host_tournament(
                name=name,
                fmt=self.format.value,
                rounds=self.rounds.value,
                turns=self.turn_time.value,
                lexicon=self.lexicon.value,
                recycle=self.recycle.value,
                capacity=self.capacity.value,
                port=port,
            )
        except Exception as exc:
            self.error = str(exc)
            self.app.toast(f"Could not create the tournament: {exc}", "error")

    def draw(self, surface) -> None:
        from .app import draw_background
        draw_background(surface, "Host a tournament", "Set the format, then invite players", left=440)
        theme.panel(surface, pygame.Rect(440, 150, 720, 640))
        theme.text(surface, "Name", 16, theme.MUTED, (470, 178))
        self.name_input.draw(surface)
        self.format.draw(surface)
        self.rounds.draw(surface)
        self.capacity.draw(surface)
        self.turn_time.draw(surface)
        self.lexicon.draw(surface)
        self.recycle.draw(surface)
        theme.text(surface, "Port", 16, theme.MUTED, (470, 566))
        self.port_input.draw(surface)
        self.create.draw(surface)
        self.back.draw(surface)
        blurb = FORMATS[self.format.value]["blurb"]
        theme.text(surface, blurb, 14, theme.MUTED, (470, 730))
        if self.error:
            theme.text(surface, self.error, 16, theme.DANGER, (470, 762))


class TournamentScreen:
    def __init__(self, app) -> None:
        self.app = app
        self.back = Button((60, 790, 170, 48), "Leave", self.leave)
        self.start = Button((820, 700, 240, 54), "Start tournament", self.start_tournament,
                            style="primary", size=20)
        self.add_bot = Button((1264, 700, 150, 54), "Add bot", self.add_bot_click)
        self.bot_level = Stepper((1086, 700, 150, 54), "", [1, 2, 3, 4, 5], 2,
                                 format_value=lambda v: f"L{v}")

    # --------------------------------------------------------------- helpers
    @property
    def snapshot(self) -> dict | None:
        return self.app.client.snapshot if self.app.client else None

    def _tournament(self) -> dict | None:
        snapshot = self.snapshot
        return (snapshot or {}).get("tournament")

    def _host(self) -> bool:
        return bool(self.app.client and self.app.client.is_host)

    def _my_id(self) -> str:
        return self.app.client.client_id if self.app.client else ""

    def _lobby_rows(self) -> list[tuple[pygame.Rect, dict]]:
        """Roster rows in the lobby, in the same order and geometry as drawn."""
        tournament = self._tournament() or {}
        rows = []
        y = 140 + 48
        for player in tournament.get("standings", []):
            rows.append((pygame.Rect(60 + 20, y, 760 - 40, 46), player))
            y += 52
        return rows

    def enter(self) -> None:
        pass

    def leave(self) -> None:
        self.app.leave_game()
        from .app import MenuScreen
        self.app.switch(MenuScreen(self.app))

    def start_tournament(self) -> None:
        if self._host() and self.app.client:
            self.app.client.host_command(action="start")

    def add_bot_click(self) -> None:
        if self._host() and self.app.client:
            self.app.client.host_command(action="add_bot", level=self.bot_level.value)

    # ---------------------------------------------------------------- events
    def handle_event(self, event) -> None:
        self.back.handle_event(event)
        tournament = self._tournament()
        if not tournament or not self._host() or tournament.get("phase") != "lobby":
            return
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 0) == 1:
            for rect, player in self._lobby_rows():
                if not player.get("is_bot"):
                    continue
                if pygame.Rect(rect.right - 80, rect.y, 80, rect.h).collidepoint(event.pos):
                    self.app.client.host_command(action="remove_participant",
                                                 client_id=player.get("client_id", ""))
                    return
        self.start.handle_event(event)
        self.add_bot.handle_event(event)
        self.bot_level.handle_event(event)

    def update(self, dt: float) -> None:
        pass

    # ------------------------------------------------------------------ draw
    def draw(self, surface) -> None:
        from .app import draw_background
        tournament = self._tournament()
        if not tournament:
            draw_background(surface, "Tournament", "Connecting...", left=60)
            theme.text(surface, "Connecting...", 22, theme.TEXT, (60, 180))
            return

        phase = tournament.get("phase")
        subtitle = f"{tournament.get('name', '')}  ·  {tournament.get('format_label', '')}"
        if phase == "lobby":
            subtitle += f"  ·  {len(tournament.get('standings', []))}/{tournament.get('capacity', 0)} players"
        elif phase == "finished":
            subtitle += "  ·  finished"
        else:
            subtitle += f"  ·  round {tournament.get('round', 0)}"
            if tournament.get("format") == "swiss":
                subtitle += f" of {tournament.get('rounds', 0)}"
        draw_background(surface, "Tournament", subtitle, left=60)

        # Standings / roster
        card = pygame.Rect(60, 140, 760, 620)
        theme.panel(surface, card)
        title = "Players" if phase == "lobby" else "Standings"
        theme.text(surface, title.upper(), 12, theme.MUTED, (card.x + 24, card.y + 18), bold=True)

        if self.app.server is not None and self.app.local_address:
            theme.text(surface, f"Share: {self.app.local_address}", 13, theme.ACCENT,
                       (card.right - 24, card.y + 18), "topright")

        standings = tournament.get("standings", [])
        y = card.y + 48
        if phase == "lobby":
            for rect, player in self._lobby_rows():
                theme.rounded_rect(surface, rect, theme.PANEL_SOFT, 8)
                dot = theme.SUCCESS if not player.get("is_bot") else theme.MUTED
                pygame.draw.circle(surface, dot, (rect.x + 20, rect.centery), 5)
                name = player["name"]
                if player.get("is_bot"):
                    name += "  (bot)"
                if player.get("away"):
                    name += "  (away)"
                if player.get("client_id") == self._my_id():
                    name += "  (you)"
                theme.text(surface, name, 17, theme.TEXT, (rect.x + 36, rect.centery), "midleft", bold=True)
                if self._host() and player.get("is_bot"):
                    theme.text(surface, "remove", 12, theme.MUTED, (rect.right - 16, rect.centery), "midright")
                y += 52
        else:
            header_y = y
            for label, x in (("#", card.x + 28), ("Player", card.x + 78), ("W", card.x + 470),
                             ("L", card.x + 530), ("D", card.x + 590)):
                theme.text(surface, label, 12, theme.MUTED, (x, header_y))
            theme.text(surface, "Spread", 12, theme.MUTED, (card.x + 700, header_y), "topright")
            pygame.draw.line(surface, theme.LINE, (card.x + 20, header_y + 20),
                             (card.right - 20, header_y + 20))
            y = header_y + 30
            for player in standings:
                rect = pygame.Rect(card.x + 14, y - 3, card.w - 28, 32)
                if player.get("rank") == 1 and phase == "finished":
                    theme.rounded_rect(surface, rect, (28, 90, 86), 6)
                color = theme.MUTED if player.get("eliminated") else theme.TEXT
                theme.text(surface, str(player.get("rank", "")), 15, theme.MUTED, (card.x + 28, y))
                theme.text(surface, player.get("name", ""), 16, color, (card.x + 78, y), bold=True)
                theme.text(surface, str(player.get("wins", 0)), 15, theme.TEXT, (card.x + 470, y))
                theme.text(surface, str(player.get("losses", 0)), 15, theme.TEXT, (card.x + 530, y))
                theme.text(surface, str(player.get("draws", 0)), 15, theme.TEXT, (card.x + 590, y))
                spread = player.get("spread", 0)
                theme.text(surface, f"{spread:+d}", 15, theme.ACCENT, (card.x + 700, y), "topright")
                y += 34

        # Matches / controls
        side = pygame.Rect(840, 140, 700, 620)
        theme.panel(surface, side)
        theme.text(surface, "MATCHES", 12, theme.MUTED, (side.x + 24, side.y + 18), bold=True)
        results = list(reversed(tournament.get("results", [])))[:11]
        y = side.y + 48
        if not results:
            theme.text(surface, "No matches yet.", 15, theme.MUTED, (side.x + 24, y))
        for result in results:
            line = result.get("a", "") + f"  {result.get('a_score', 0)}"
            other = f"{result.get('b_score', 0)}  " + result.get("b", "")
            if result.get("kind") == "bye":
                theme.text(surface, f"R{result.get('round')}  {result.get('a')}  bye", 14, theme.MUTED, (side.x + 24, y))
            elif result.get("kind") == "walkover":
                theme.text(surface, f"R{result.get('round')}  {result.get('winner')}  walkover", 14,
                           theme.MUTED, (side.x + 24, y))
            else:
                winner = result.get("winner")
                a_color = theme.ACCENT if winner == result.get("a") else theme.TEXT
                b_color = theme.ACCENT if winner == result.get("b") else theme.TEXT
                theme.text(surface, f"R{result.get('round')}", 13, theme.MUTED, (side.x + 24, y))
                theme.text(surface, line, 15, a_color, (side.x + 70, y))
                theme.text(surface, "–", 15, theme.MUTED, (side.x + 300, y), "topright")
                theme.text(surface, other, 15, b_color, (side.x + 320, y))
            y += 26

        status_y = side.bottom - 96
        if phase == "playing":
            pair = tournament.get("current") or {}
            theme.text(surface, f"Playing: {pair.get('a', '?')} vs {pair.get('b', '?')}",
                       16, theme.SUCCESS, (side.x + 24, status_y), bold=True)
        elif phase == "between":
            seconds = int(tournament.get("next_start", 0))
            theme.text(surface, f"Next match in {seconds}s", 16, theme.MUTED, (side.x + 24, status_y))
        elif phase == "lobby":
            if self._host():
                theme.text(surface, "Add bots, then start when everyone has joined.",
                           15, theme.MUTED, (side.x + 24, status_y))
                self.bot_level.draw(surface)
                self.add_bot.draw(surface)
                self.start.draw(surface)
            else:
                theme.text(surface, "Waiting for the host to start...", 16, theme.TEXT, (side.x + 24, status_y))
        elif phase == "finished":
            champion = tournament.get("champion") or "nobody"
            theme.text(surface, f"Champion: {champion}", 20, theme.ACCENT, (side.x + 24, status_y), bold=True)

        self.back.draw(surface)
        if phase == "finished" and self._host():
            theme.text(surface, "Start a new tournament from the menu.", 13, theme.MUTED, (60, 850))
