"""Application shell: menu, setup, lobby and results screens."""

from __future__ import annotations

import json
import os
import threading

import pygame

from ..bot import level_info
from ..lexicon import (
    lexicon_label,
    lexicon_names,
    lexicon_note,
    resolve as resolve_lexicon,
)
from ..net.client import NetClient
from ..net.server import GameServer, local_ip, public_ip
from ..session import Session
from ..tiles import LETTER_VALUES
from . import theme
from .widgets import Button, Stepper, TextInput, Toggle, Toast

SIZE = (1600, 900)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", ROOT), "Tessera")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")
TURN_CHOICES = [60, 90, 120, 180]

DEFAULT_SETTINGS = {
    "name": "Player",
    "opponents": 1,
    "turn_seconds": 120,
    "allow_blank_recycle": True,
    "allow_hints": True,
    "lexicon": "csw",
    "fullscreen": False,
    "highlight_last_move": True,
    "show_coordinates": True,
    "bingo_bonus": True,
    "end_after_six_scoreless": True,
    "minimum_word_length": 0,
    "port": "5467",
}


def make_lexicon_stepper(rect, current=None, on_change=None) -> Stepper:
    """A word-list chooser built from whatever lists this machine has."""
    names = lexicon_names() or ["csw"]
    chosen = current if current in names else names[0]
    return Stepper(rect, "Word list", names, names.index(chosen), on_change,
                   format_value=lexicon_label)


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    except OSError:
        pass


class Screen:
    def __init__(self, app: "App") -> None:
        self.app = app

    def enter(self) -> None:
        pass

    def handle_event(self, event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface) -> None:
        pass


def draw_background(surface, title: str | None = None, subtitle: str | None = None, left: int = 60):
    theme.vgradient(surface, pygame.Rect(0, 0, *surface.get_size()), (18, 72, 75), theme.BG_DARK)
    if title:
        theme.heading(surface, title, 46, (left, 44))
    if subtitle:
        theme.text(surface, subtitle, 18, theme.MUTED, (left + 2, 100))


# Where the complete source is published. GPL v3+ requires this to be real
# before the Store listing goes live - see tools/build_msix.py for identity.
SOURCE_URL = "https://github.com/your-account/tessera"  # TODO: set before submission


class MenuScreen(Screen):
    def enter(self) -> None:
        y = 330
        self.buttons = [
            Button((60, y, 330, 56), "Play against the computer", self.local, style="primary", size=20),
            Button((60, y + 70, 330, 56), "Host an online game", self.host, size=20),
            Button((60, y + 140, 330, 56), "Host a tournament", self.host_tournament, size=20),
            Button((60, y + 210, 330, 56), "Join an online game", self.join, size=20),
            Button((60, y + 282, 330, 44), "How to play", self.howto, size=17),
            Button((60, y + 332, 330, 44), "Settings", self.settings_screen, size=17),
            Button((60, y + 382, 330, 44), "About and licences", self.about, size=17),
            Button((60, y + 432, 330, 44), "Quit", self.app.quit, size=17),
        ]

    def local(self):
        self.app.switch(LocalSetupScreen(self.app))

    def host(self):
        self.app.switch(HostSetupScreen(self.app))

    def join(self):
        self.app.switch(JoinScreen(self.app))

    def host_tournament(self):
        from .tournament_screen import TournamentSetupScreen
        self.app.switch(TournamentSetupScreen(self.app))

    def howto(self):
        self.app.switch(HowToScreen(self.app))

    def settings_screen(self):
        from .settings_screen import SettingsScreen
        self.app.switch(SettingsScreen(self.app))

    def about(self):
        self.app.switch(AboutScreen(self.app))

    def handle_event(self, event):
        for button in self.buttons:
            if button.handle_event(event):
                return

    def draw(self, surface):
        draw_background(surface)
        letters = "TESSERA"
        x = 60
        for i, letter in enumerate(letters):
            rect = pygame.Rect(x + i * 78, 150, 70, 70)
            theme.draw_tile(surface, rect, letter, LETTER_VALUES.get(letter, 1), value_color=theme.ACCENT_DARK)
        current = self.app.settings.get("lexicon")
        theme.text(surface, f"{lexicon_label(current)} word list  ·  Quackle engine  ·  2-4 players online",
                   19, theme.MUTED, (62, 244))
        theme.text(surface, "SEVEN TILES.  INFINITE WORDS.", 13, theme.ACCENT, (64, 274), bold=True)
        for button in self.buttons:
            button.draw(surface)

        card = pygame.Rect(980, 170, 470, 380)
        theme.panel(surface, card)
        theme.text(surface, "Built for club play", 22, theme.TEXT, (card.x + 28, card.y + 24), bold=True)
        identity_voice = lexicon_note(current) or "Word list"
        points = [
            (lexicon_label(current), identity_voice),
            ("Quackle", "the engine behind the bot's five skill levels"),
            ("Online", "2 to 4 players, or unlimited spectators"),
            ("Clocks", "1 to 3 minutes per turn, shown at the top"),
            ("House rule", "recycle the blanks once per game"),
        ]
        y = card.y + 76
        for label, body in points:
            theme.text(surface, label, 15, theme.ACCENT, (card.x + 28, y), bold=True)
            theme.text(surface, body, 15, theme.TEXT, (card.x + 128, y))
            y += 52
        theme.text(surface, "v1.0  ·  F:\\Tessera", 14, (96, 128, 114), (62, 882))


class HowToScreen(Screen):
    def enter(self):
        self.back = Button((240, 760, 160, 48), "Back", lambda: self.app.switch(MenuScreen(self.app)))

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.switch(MenuScreen(self.app))
        self.back.handle_event(event)

    def draw(self, surface):
        draw_background(surface, "How to play", "A quick reminder of the rules", left=240)
        lines = [
            ("Place tiles", "Click a tile on your rack, then click a square. Click a placed tile to take it back."),
            ("Scoring", "A play must join the tiles on the board. The first play must cross the centre star."),
            ("Bonus squares", "TW = triple word, DW = double word, TL = triple letter, DL = double letter."),
            ("Bingo", "Playing all seven tiles in one turn scores 50 extra points."),
            ("Blanks", "A blank scores zero. Pick its letter when you place it."),
            ("Exchange", "Swap tiles with the bag. Only when the bag holds seven or more tiles."),
            ("Blank recycle", "Optional house rule: each player may return their blank to the bag once per game."),
            ("Clock", "Each turn has its own clock. Run out and your turn is passed."),
            ("Online", "The host runs the game server and shares an address. Everyone needs this game installed."),
            ("Settings", "Esc during a game opens Settings. Match rules stay locked while a match is running."),
        ]
        y = 190
        for title, body in lines:
            theme.text(surface, title, 21, theme.ACCENT, (240, y), bold=True)
            for i, line in enumerate(theme.wrap_text(body, 19, 900)):
                theme.text(surface, line, 19, theme.TEXT, (430, y + i * 26))
            y += 26 * max(1, len(theme.wrap_text(body, 19, 900))) + 22
        self.back.draw(surface)


class AboutScreen(Screen):
    def enter(self):
        self.back = Button((240, 760, 160, 48), "Back", lambda: self.app.switch(MenuScreen(self.app)))

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.switch(MenuScreen(self.app))
        self.back.handle_event(event)

    def draw(self, surface):
        draw_background(surface, "About Tessera", "Version 1.0", left=240)
        lines = [
            ("Licence", "Tessera is free software under the GNU GPL version 3 or "
                        "later. You may run, study, change and share it."),
            ("Source code", "The complete source code is published at " + SOURCE_URL),
            ("Quackle", "The bot runs on Quackle by Jason Katz-Brown, John "
                        "O'Laughlin and John Fultz, also GPL v3 or later "
                        "(github.com/quackle)."),
            ("Word list", "This build ships the free ENABLE word list. Imported "
                          "lists stay on your computer and are not redistributed."),
            ("Trademark", "Tessera is an independent word game, not affiliated "
                          "with or endorsed by Mattel or Hasbro."),
            ("Warranty", "None. See the LICENCE and THIRD-PARTY-LICENCES files "
                         "shipped with the game for details."),
        ]
        y = 190
        for title, body in lines:
            theme.text(surface, title, 21, theme.ACCENT, (240, y), bold=True)
            wrapped = theme.wrap_text(body, 19, 900)
            for i, line in enumerate(wrapped):
                theme.text(surface, line, 19, theme.TEXT, (430, y + i * 26))
            y += 26 * len(wrapped) + 22
        self.back.draw(surface)


class LocalSetupScreen(Screen):
    def enter(self):
        settings = self.app.settings
        self.name_input = TextInput((470, 190, 440, 46), "Your name", 18, settings.get("name", "Player"))
        self.opponents = Stepper((470, 258, 440, 40), "Computer opponents", [1, 2, 3], int(settings.get("opponents", 1)) - 1)
        self.levels = [
            Stepper((470, 318 + i * 64, 440, 40), f"Opponent {i + 1} skill", [1, 2, 3, 4, 5],
                    int(settings.get(f"level{i}", 3)) - 1,
                    format_value=lambda value: level_info(value)["name"])
            for i in range(3)
        ]
        self.turn_time = Stepper((470, 526, 440, 40), "Clock per turn", TURN_CHOICES,
                                 TURN_CHOICES.index(int(settings.get("turn_seconds", 120))) if int(settings.get("turn_seconds", 120)) in TURN_CHOICES else 2,
                                 format_value=lambda value: f"{value // 60} min")
        self.recycle = Toggle((470, 574, 440, 40), "Allow one blank recycle per player",
                              bool(settings.get("allow_blank_recycle", True)))
        self.lexicon = make_lexicon_stepper((470, 622, 440, 40), settings.get("lexicon"))
        self.start = Button((470, 676, 250, 54), "Start game", self.start_game, style="primary", size=20)
        self.back = Button((736, 676, 154, 54), "Back", lambda: self.app.switch(MenuScreen(self.app)))
        self.error = ""
        self._level_rows = 0

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.switch(MenuScreen(self.app))
            return
        for widget in [self.name_input, self.opponents, *self.levels, self.turn_time, self.recycle,
                       self.lexicon, self.start, self.back]:
            if widget.handle_event(event):
                return

    def start_game(self):
        name = self.name_input.value.strip() or "Player"
        opponents = self.opponents.value
        levels = [self.levels[i].value for i in range(opponents)]
        self.app.settings.update({
            "name": name,
            "opponents": opponents,
            "turn_seconds": self.turn_time.value,
            "allow_blank_recycle": self.recycle.value,
            "lexicon": self.lexicon.value,
        })
        for i, level in enumerate(levels):
            self.app.settings[f"level{i}"] = level
        save_settings(self.app.settings)
        try:
            self.app.start_local(name, levels, self.turn_time.value, self.recycle.value, self.lexicon.value)
        except Exception as exc:
            self.error = str(exc)
            self.app.toast(f"Could not start: {exc}", "error")

    def draw(self, surface):
        draw_background(surface, "Play against the computer", "Set the table, then start", left=440)
        theme.panel(surface, pygame.Rect(440, 150, 720, 600))
        theme.text(surface, "Name", 17, theme.MUTED, (470, 168))
        self.name_input.draw(surface)
        self.opponents.draw(surface)
        for i, stepper in enumerate(self.levels):
            if i >= self.opponents.value:
                continue
            stepper.draw(surface)
            info = level_info(stepper.value)
            theme.text(surface, info["blurb"], 14, theme.MUTED, (470, 360 + i * 64))
        self.turn_time.draw(surface)
        self.recycle.draw(surface)
        self.lexicon.draw(surface)
        self.start.draw(surface)
        self.back.draw(surface)
        if self.error:
            theme.text(surface, self.error, 16, theme.DANGER, (470, 736))


class HostSetupScreen(Screen):
    def enter(self):
        settings = self.app.settings
        self.name_input = TextInput((510, 190, 420, 46), "Your name", 18, settings.get("name", "Host"))
        self.seats = Stepper((510, 258, 420, 40), "Seats (including you)", [2, 3, 4], int(settings.get("seats", 2)) - 2)
        self.turn_time = Stepper((510, 312, 420, 40), "Clock per turn", TURN_CHOICES,
                                 TURN_CHOICES.index(int(settings.get("turn_seconds", 120))) if int(settings.get("turn_seconds", 120)) in TURN_CHOICES else 2,
                                 format_value=lambda value: f"{value // 60} min")
        self.recycle = Toggle((510, 358, 420, 40), "Allow one blank recycle per player",
                              bool(settings.get("allow_blank_recycle", True)))
        self.lexicon = make_lexicon_stepper((510, 402, 420, 40), settings.get("lexicon"))
        self.port_input = TextInput((510, 476, 200, 46), "Port", 5, str(settings.get("port", "5467")))
        self.host = Button((510, 548, 250, 56), "Create server", self.create, style="primary", size=20)
        self.back = Button((776, 548, 154, 56), "Back", lambda: self.app.switch(MenuScreen(self.app)))
        self.error = ""

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.switch(MenuScreen(self.app))
            return
        for widget in [self.name_input, self.seats, self.turn_time, self.recycle, self.lexicon,
                       self.port_input, self.host, self.back]:
            if widget.handle_event(event):
                return

    def create(self):
        name = self.name_input.value.strip() or "Host"
        try:
            port = int(self.port_input.value or "5467")
        except ValueError:
            self.error = "Port must be a number."
            return
        self.app.settings.update({
            "name": name,
            "seats": self.seats.value,
            "turn_seconds": self.turn_time.value,
            "allow_blank_recycle": self.recycle.value,
            "lexicon": self.lexicon.value,
            "port": str(port),
        })
        save_settings(self.app.settings)
        try:
            self.app.host_game(name, self.seats.value, self.turn_time.value, self.recycle.value, port, self.lexicon.value)
        except Exception as exc:
            self.error = str(exc)
            self.app.toast(f"Could not host: {exc}", "error")

    def draw(self, surface):
        draw_background(surface, "Host an online game", "Your PC becomes the game server", left=490)
        theme.panel(surface, pygame.Rect(490, 165, 620, 470))
        theme.text(surface, "Name", 17, theme.MUTED, (510, 168))
        self.name_input.draw(surface)
        self.seats.draw(surface)
        self.turn_time.draw(surface)
        self.recycle.draw(surface)
        self.lexicon.draw(surface)
        theme.text(surface, "Port", 17, theme.MUTED, (510, 454))
        self.port_input.draw(surface)
        theme.text(surface, "You may need to allow the game through your firewall or forward this port.", 14, theme.MUTED, (730, 489))
        self.host.draw(surface)
        self.back.draw(surface)
        if self.error:
            theme.text(surface, self.error, 16, theme.DANGER, (510, 612))


class JoinScreen(Screen):
    def enter(self):
        settings = self.app.settings
        self.address = TextInput((585, 250, 420, 46), "host address, e.g. 192.168.1.20:5467", 60,
                                 settings.get("last_address", ""))
        self.name_input = TextInput((585, 336, 420, 46), "Your name", 18, settings.get("name", "Player"))
        self.connect = Button((585, 414, 140, 56), "Join game", self.do_connect, style="primary", size=19)
        self.watch = Button((737, 414, 140, 56), "Spectate", self.do_spectate, size=19)
        self.back = Button((889, 414, 120, 56), "Back", lambda: self.app.switch(MenuScreen(self.app)))
        self.error = ""
        self._observe = False

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.switch(MenuScreen(self.app))
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self.do_connect()
            return
        for widget in [self.address, self.name_input, self.connect, self.watch, self.back]:
            if widget.handle_event(event):
                return

    def do_spectate(self):
        self.do_connect(True)

    def do_connect(self, observe: bool = False):
        self._observe = observe
        address = self.address.value.strip()
        name = self.name_input.value.strip() or "Player"
        if ":" not in address:
            self.error = "Use address:port, for example 192.168.1.20:5467"
            return
        host, _, port_text = address.rpartition(":")
        try:
            port = int(port_text)
        except ValueError:
            self.error = "The port must be a number."
            return
        self.app.settings.update({"name": name, "last_address": address})
        save_settings(self.app.settings)
        ok = self.app.join_game(host, port, name, observe=self._observe)
        if not ok:
            self.error = self.app.client.connect_error if self.app.client else "Could not connect."
        else:
            self.app.switch(LobbyScreen(self.app))

    def draw(self, surface):
        draw_background(surface, "Join an online game", "Ask the host for their address", left=565)
        theme.panel(surface, pygame.Rect(565, 200, 470, 350))
        theme.text(surface, "Server address", 17, theme.MUTED, (585, 218))
        self.address.draw(surface)
        theme.text(surface, "Name", 17, theme.MUTED, (585, 306))
        self.name_input.draw(surface)
        self.connect.draw(surface)
        self.watch.draw(surface)
        self.back.draw(surface)
        theme.text(surface, "Spectate watches the game without taking a seat.", 13, theme.MUTED, (585, 480))
        if self.error:
            theme.text(surface, self.error, 16, theme.DANGER, (585, 506))


class LobbyScreen(Screen):
    def enter(self):
        self.error = ""
        self.public = ""
        threading.Thread(target=self._lookup_public_ip, daemon=True).start()
        self.start_button = Button((440, 756, 240, 54), "Start match", self.start_match, style="primary", size=20)
        self.leave_button = Button((700, 756, 140, 54), "Leave", self.leave)
        self.settings_button = Button((856, 756, 150, 54), "Settings", self.open_settings)
        self.seat_buttons = []
        self.level_steppers = []
        self.seats_stepper = Stepper((228, 590, 420, 36), "Seats", [2, 3, 4], 0)
        self.turn_stepper = Stepper((228, 630, 420, 36), "Clock per turn", TURN_CHOICES, 2,
                                    format_value=lambda v: f"{v // 60} min")
        self.lexicon_stepper = make_lexicon_stepper((228, 670, 420, 36))
        self._sync_settings = False

    def _lookup_public_ip(self):
        self.public = public_ip()

    def leave(self):
        self.app.leave_game()
        self.app.switch(MenuScreen(self.app))

    def open_settings(self):
        from .settings_screen import SettingsScreen
        self.app.switch(SettingsScreen(self.app, back_target=self))

    def _host(self) -> bool:
        return bool(self.app.client and self.app.client.is_host)

    def start_match(self):
        if not self._host():
            return
        self.app.client.host_command(action="start")

    def handle_event(self, event):
        snapshot = self.app.client.snapshot if self.app.client else None
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.leave()
            return
        self.settings_button.handle_event(event)
        self.leave_button.handle_event(event)
        if not self._host() or snapshot is None:
            return
        self.start_button.handle_event(event)
        self.seats_stepper.handle_event(event)
        self.turn_stepper.handle_event(event)
        self.lexicon_stepper.handle_event(event)
        for index, (stepper, _button) in enumerate(zip(self.level_steppers, self.seat_buttons)):
            if stepper.handle_event(event):
                self.app.client.host_command(action="add_bot", seat=index, level=stepper.value)
            if _button.handle_event(event):
                seat = snapshot["seats"][index] if index < len(snapshot["seats"]) else None
                if seat and seat["is_bot"]:
                    self.app.client.host_command(action="remove_bot", seat=index)
                else:
                    self.app.client.host_command(action="add_bot", seat=index, level=stepper.value)

    def update(self, dt):
        snapshot = self.app.client.snapshot if self.app.client else None
        if snapshot is None:
            return
        if self._host():
            settings = snapshot["settings"]
            if not self._sync_settings:
                self.seats_stepper.set_value(settings["max_seats"])
                self.turn_stepper.set_value(settings["turn_seconds"])
                self.lexicon_stepper.set_value(settings.get("lexicon", "csw"))
                self._last_sent = (self.seats_stepper.value, self.turn_stepper.value, self.lexicon_stepper.value)
                self._sync_settings = True
            wanted = (self.seats_stepper.value, self.turn_stepper.value, self.lexicon_stepper.value)
            if wanted != getattr(self, "_last_sent", None):
                self._last_sent = wanted
                self.app.client.host_command(action="settings", seats=wanted[0], turn_seconds=wanted[1],
                                             lexicon=wanted[2])
        if snapshot.get("phase") in ("playing", "finished"):
            from .game_screen import GameScreen
            self.app.switch(GameScreen(self.app))

    def draw(self, surface):
        draw_background(surface, "Lobby", "Waiting for players", left=200)
        snapshot = self.app.client.snapshot if self.app.client else None
        if snapshot is None:
            theme.text(surface, "Connecting...", 22, theme.TEXT, (200, 200))
            return

        theme.panel(surface, pygame.Rect(200, 140, 640, 600))
        address = snapshot.get("address", "")
        theme.text(surface, "Server address", 16, theme.MUTED, (228, 162))
        theme.text(surface, address or "starting...", 26, theme.ACCENT, (228, 186), bold=True)
        hint = "Give this address to your friends. They choose Join an online game."
        for i, line in enumerate(theme.wrap_text(hint, 15, 580)):
            theme.text(surface, line, 15, theme.MUTED, (228, 224 + i * 20))
        if self.public:
            theme.text(surface, f"Public IP: {self.public}", 15, theme.MUTED, (228, 266))
        watching = snapshot.get("observers", [])
        theme.text(surface, "Players", 17, theme.MUTED, (228, 300))
        if watching:
            theme.text(surface, f"{len(watching)} watching", 14, theme.ACCENT, (780, 304), "topright")

        seats = snapshot["seats"]
        self.seat_buttons = []
        self.level_steppers = []
        for index, seat in enumerate(seats):
            y = 330 + index * 58
            rect = pygame.Rect(228, y, 584, 50)
            theme.rounded_rect(surface, rect, theme.PANEL_SOFT, 10)
            dot = theme.SUCCESS if seat["connected"] else theme.MUTED
            pygame.draw.circle(surface, dot, (rect.x + 22, rect.centery), 6)
            name = seat["name"] + ("  (you)" if self.app.client and self.app.client.seat == index else "")
            theme.text(surface, name, 19, theme.TEXT, (rect.x + 42, rect.centery), "midleft", bold=True)
            if seat["is_bot"]:
                stepper = Stepper((rect.right - 300, y + 5, 190, 40), "", [1, 2, 3, 4, 5], seat["level"] - 1,
                                  format_value=lambda v: level_info(v)["name"])
                stepper.draw(surface)
                self.level_steppers.append(stepper)
                button = Button((rect.right - 104, y + 8, 92, 34), "Remove", style="ghost", size=15)
                self.seat_buttons.append(button)
                button.draw(surface)
            else:
                if seat["taken"] and not seat["connected"]:
                    state_label = "Away"
                elif seat["taken"]:
                    state_label = "Ready"
                else:
                    state_label = "Waiting"
                theme.text(surface, state_label, 16, theme.MUTED,
                           (rect.right - (118 if self._host() and not seat["taken"] else 24), rect.centery), "midright")
                self.level_steppers.append(Stepper((rect.right - 300, y + 5, 190, 40), "", [1, 2, 3, 4, 5], 2))
                button = Button((rect.right - 104, y + 8, 92, 34), "Add bot", size=15)
                self.seat_buttons.append(button)
                if self._host() and not seat["taken"]:
                    button.draw(surface)

        if self.app.client and self.app.client.observer:
            theme.text(surface, "You are spectating. The host starts the match.", 15, theme.SUCCESS, (440, 700))
        if self._host():
            self.seats_stepper.draw(surface)
            self.turn_stepper.draw(surface)
            self.lexicon_stepper.draw(surface)
            self.start_button.draw(surface)
            theme.text(surface, "The host starts the match when everyone is in.", 15, theme.MUTED, (440, 820))
        else:
            host_settings = snapshot["settings"]
            theme.text(surface,
                       f"{host_settings.get('max_seats', 2)} seats · {host_settings['turn_seconds'] // 60} min per turn · "
                       f"{host_settings.get('lexicon_label', 'CSW24')} · "
                       f"{'blank recycle on' if host_settings.get('allow_blank_recycle') else 'no blank recycle'}",
                       15, theme.MUTED, (440, 748))
            theme.text(surface, "Waiting for the host to start the match...", 19, theme.TEXT, (440, 776))
        self.settings_button.draw(surface)
        self.leave_button.draw(surface)


class ResultsScreen(Screen):
    def enter(self):
        self.rematch = Button((420, 700, 200, 54), "Rematch", self.do_rematch, style="primary", size=20)
        self.rematch.enabled = bool(self.app.client and self.app.client.is_host)
        self.analysis = Button((636, 700, 220, 54), "Analyse my play", self.do_analysis, size=20)
        self.analysis.enabled = bool(self.app.client and not self.app.client.observer)
        self.menu = Button((872, 700, 180, 54), "Main menu", self.leave)
        self.done = False

    def do_rematch(self):
        if self.app.client and self.app.client.is_host:
            if self.app.client:
                self.app.client.analysis = None
            self.app.client.host_command(action="rematch")
            from .game_screen import GameScreen
            self.app.switch(GameScreen(self.app))

    def do_analysis(self):
        if self.app.client is None:
            return
        self.app.client.ask_analysis()
        from .analysis_screen import AnalysisScreen
        self.app.switch(AnalysisScreen(self.app, back_target=self))

    def leave(self):
        self.app.leave_game()
        self.app.switch(MenuScreen(self.app))

    def handle_event(self, event):
        self.rematch.handle_event(event)
        self.analysis.handle_event(event)
        self.menu.handle_event(event)

    def update(self, dt):
        if self.done or not self.app.client:
            return
        snapshot = self.app.client.snapshot
        if snapshot and snapshot.get("phase") == "playing":
            self.done = True
            from .game_screen import GameScreen
            self.app.switch(GameScreen(self.app))

    def draw(self, surface):
        draw_background(surface, "Final scores", "", left=240)
        snapshot = self.app.client.snapshot if self.app.client else None
        if not snapshot or not snapshot.get("state"):
            return
        state = snapshot["state"]
        theme.text(surface, state.get("result", ""), 22, theme.ACCENT, (240, 140), bold=True)
        players = sorted(state["players"], key=lambda p: p["score"], reverse=True)
        for index, player in enumerate(players):
            y = 200 + index * 92
            rect = pygame.Rect(240, y, 1000, 76)
            theme.rounded_rect(surface, rect, theme.PANEL if index else theme.PANEL_HI, 12)
            medal = ["1st", "2nd", "3rd", "4th"][index]
            theme.text(surface, medal, 18, theme.MUTED, (rect.x + 22, rect.centery), "midleft")
            theme.text(surface, player["name"], 24, theme.TEXT, (rect.x + 80, rect.centery), "midleft", bold=True)
            theme.text(surface, player["score"], 30, theme.ACCENT, (rect.right - 30, rect.centery), "midright", bold=True)
            theme.text(surface, f"{player['tiles_left']} tiles left", 15, theme.MUTED, (rect.right - 140, rect.centery), "midright")
        self.rematch.draw(surface)
        self.analysis.draw(surface)
        self.menu.draw(surface)
        theme.text(surface, "Analysis reviews your own moves against Quackle's best play.", 14, theme.MUTED, (420, 766))


class App:
    def __init__(self) -> None:
        pygame.init()
        self.settings = {**DEFAULT_SETTINGS, **load_settings()}
        # Never start pointing at a word list that is not on this machine
        # (the Store build ships ENABLE, not the Collins lists).
        self.settings["lexicon"] = resolve_lexicon(self.settings.get("lexicon"))
        pygame.display.set_caption(f"Tessera - {lexicon_label(self.settings['lexicon'])}")
        # Everything is drawn on a fixed 1240x880 canvas and scaled to the window
        # with a smooth filter, so text stays crisp at any size or resolution.
        self.canvas = pygame.Surface(SIZE)
        self.surface = self.canvas
        self.window = self._open_window()
        self._view_scale = 1.0
        self._view_offset = (0, 0)
        self.clock = pygame.time.Clock()
        self.running = True
        self._set_window_icon()
        self.client: NetClient | None = None
        self.server: GameServer | None = None
        self.session: Session | None = None
        self.tournament = None
        self.local_address = ""
        self.toasts: list[Toast] = []
        self._was_disconnected = False
        self._dim: pygame.Surface | None = None
        self.screen: Screen = MenuScreen(self)
        self.screen.enter()

    def _headless(self) -> bool:
        return bool(os.environ.get("TESSERA_HEADLESS"))

    def _open_window(self):
        if self._headless():
            return pygame.display.set_mode(SIZE)
        fullscreen = bool(self.settings.get("fullscreen"))
        try:
            if fullscreen:
                return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            return pygame.display.set_mode(SIZE, pygame.RESIZABLE)
        except pygame.error:
            self.settings["fullscreen"] = False
            return pygame.display.set_mode(SIZE, pygame.RESIZABLE)

    def apply_display_preferences(self) -> None:
        if self._headless():
            return
        fullscreen = bool(self.settings.get("fullscreen"))
        try:
            if fullscreen:
                self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                self.window = pygame.display.set_mode(SIZE, pygame.RESIZABLE)
                if self.window.get_size() != SIZE:
                    # SDL sometimes keeps the full-screen display mode for one
                    # call after leaving full screen; a second request restores
                    # the windowed size (and is harmless when the desktop is
                    # simply smaller than the canvas).
                    self.window = pygame.display.set_mode(SIZE, pygame.RESIZABLE)
        except pygame.error:
            # Never leave the player without a window.
            self.settings["fullscreen"] = False
            try:
                self.window = pygame.display.set_mode(SIZE, pygame.RESIZABLE)
            except pygame.error:
                pass
            return
        self._set_window_icon()

    def _set_window_icon(self) -> None:
        try:
            icon = pygame.image.load(os.path.join(ROOT, "assets", "icon.png"))
            pygame.display.set_icon(icon)
            return
        except (pygame.error, FileNotFoundError, OSError):
            pass
        if self._headless():
            return
        icon = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.rect(icon, (198, 84, 62), (2, 2, 60, 60), border_radius=12)
        pygame.draw.rect(icon, (246, 240, 222), (8, 8, 48, 48), border_radius=9)
        letter = theme.font(34, True, "georgia").render("S", True, (38, 40, 38))
        icon.blit(letter, letter.get_rect(center=(32, 32)))
        pygame.display.set_icon(icon)

    # ------------------------------------------------------------------ utils
    def switch(self, screen: Screen) -> None:
        self.screen = screen
        self.screen.enter()

    def toast(self, message: str, kind: str = "info") -> None:
        self.toasts.append(Toast(message, kind))
        self.toasts = self.toasts[-4:]

    def quit(self) -> None:
        self.running = False

    # ------------------------------------------------------------------ games
    def _local_session(self, name: str, levels: list[int], turn_seconds: int, recycle: bool) -> Session:
        session = Session(turn_seconds=turn_seconds, allow_blank_recycle=recycle, seats=len(levels) + 1)
        session.seat_list[0].name = name
        session.seat_list[0].level = 3
        for index, level in enumerate(levels, start=1):
            session.add_bot(index, level)
        session.start()
        return session

    def start_local(self, name: str, levels: list[int], turn_seconds: int, recycle: bool,
                    lexicon: str = "csw") -> None:
        self.leave_game()
        session = Session(
            turn_seconds=turn_seconds, allow_blank_recycle=recycle, seats=len(levels) + 1,
            lexicon=lexicon, allow_hints=bool(self.settings.get("allow_hints", True)),
            bingo_bonus=bool(self.settings.get("bingo_bonus", True)),
            end_after_six_scoreless=bool(self.settings.get("end_after_six_scoreless", True)),
            minimum_word_length=int(self.settings.get("minimum_word_length", 0)),
        )
        self.session = session
        server = GameServer(session, port=0, host="127.0.0.1")
        port = server.start()
        self.server = server
        client = NetClient()
        if not client.connect("127.0.0.1", port, name):
            raise RuntimeError(client.connect_error or "Could not reach the local server.")
        self.client = client
        for index, level in enumerate(levels, start=1):
            session.add_bot(index, level)
        session.start()
        from .game_screen import GameScreen
        self.switch(GameScreen(self))

    def host_game(self, name: str, seats: int, turn_seconds: int, recycle: bool, port: int,
                  lexicon: str = "csw") -> None:
        self.leave_game()
        session = Session(
            turn_seconds=turn_seconds, allow_blank_recycle=recycle, seats=seats, lexicon=lexicon,
            allow_hints=bool(self.settings.get("allow_hints", True)),
            bingo_bonus=bool(self.settings.get("bingo_bonus", True)),
            end_after_six_scoreless=bool(self.settings.get("end_after_six_scoreless", True)),
            minimum_word_length=int(self.settings.get("minimum_word_length", 0)),
        )
        server = GameServer(session, port=port, host="0.0.0.0")
        bound = server.start()
        session.address = f"{local_ip()}:{bound}"
        self.server = server
        self.session = session
        client = NetClient()
        if not client.connect("127.0.0.1", bound, name):
            raise RuntimeError(client.connect_error or "Could not reach the local server.")
        self.client = client
        self.switch(LobbyScreen(self))

    def host_tournament(self, name: str, fmt: str, rounds: int, turns: int, lexicon: str,
                        recycle: bool, capacity: int, port: int) -> None:
        from ..tournament import Tournament
        from .tournament_screen import TournamentScreen

        self.leave_game()
        tournament = Tournament(
            name=name, fmt=fmt, rounds=rounds, turn_seconds=turns, lexicon=lexicon,
            allow_blank_recycle=recycle, allow_hints=bool(self.settings.get("allow_hints", True)),
            bingo_bonus=bool(self.settings.get("bingo_bonus", True)),
            end_after_six_scoreless=bool(self.settings.get("end_after_six_scoreless", True)),
            minimum_word_length=int(self.settings.get("minimum_word_length", 0)),
            capacity=capacity,
        )
        server = GameServer(None, port=port, host="0.0.0.0", tournament=tournament)
        bound = server.start()
        self.local_address = f"{local_ip()}:{bound}"
        self.server = server
        self.tournament = tournament
        client = NetClient()
        if not client.connect("127.0.0.1", bound, self.settings.get("name", "Host")):
            raise RuntimeError(client.connect_error or "Could not reach the local server.")
        self.client = client
        self.switch(TournamentScreen(self))

    def join_game(self, host: str, port: int, name: str, observe: bool = False) -> bool:
        self.leave_game()
        client = NetClient()
        if not client.connect(host, port, name, observe=observe):
            self.client = client
            return False
        self.client = client
        return True

    def leave_game(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.server is not None:
            self.server.stop()
            self.server = None
        self.session = None
        self.tournament = None
        self.local_address = ""

    def _present(self) -> None:
        """Scale the canvas to the window, letterboxed and smoothly."""
        width, height = self.window.get_size()
        if (width, height) == SIZE:
            self.window.blit(self.canvas, (0, 0))
            self._view_scale = 1.0
            self._view_offset = (0, 0)
        else:
            scale = min(width / SIZE[0], height / SIZE[1])
            target = (max(1, int(SIZE[0] * scale)), max(1, int(SIZE[1] * scale)))
            scaled = pygame.transform.smoothscale(self.canvas, target)
            offset_x = (width - target[0]) // 2
            offset_y = (height - target[1]) // 2
            self.window.fill((5, 30, 32))
            self.window.blit(scaled, (offset_x, offset_y))
            self._view_scale = scale
            self._view_offset = (offset_x, offset_y)
        pygame.display.flip()

    def _map_event(self, event):
        if self._view_scale == 1.0 and self._view_offset == (0, 0):
            return event
        position = getattr(event, "pos", None)
        if position is None:
            return event
        offset_x, offset_y = self._view_offset
        event.pos = (
            int((position[0] - offset_x) / self._view_scale),
            int((position[1] - offset_y) / self._view_scale),
        )
        return event

    def _watch_connection(self) -> None:
        """Toast the drop, then the return; leave the table if the seat is gone."""
        client = self.client
        if client is None:
            return
        if client.connected:
            if self._was_disconnected:
                self._was_disconnected = False
                self.toast("Back in the game.", "info")
            return
        self._was_disconnected = True
        if client.gave_up or client.reconnect_refused:
            message = client.reconnect_refused or "Could not reconnect. Your seat was given up."
            self.toast(message, "error")
            self.leave_game()
            self.switch(MenuScreen(self))

    def _draw_connection_banner(self) -> None:
        """A dimmed card while the client is trying to get back in."""
        client = self.client
        if client is None or client.connected:
            return
        if self._dim is None:
            self._dim = pygame.Surface(SIZE, pygame.SRCALPHA)
            self._dim.fill((4, 18, 19, 150))
        self.canvas.blit(self._dim, (0, 0))
        card = pygame.Rect(0, 0, 560, 150)
        card.center = (SIZE[0] // 2, SIZE[1] // 2)
        theme.rounded_rect(self.canvas, card, theme.BG_DARK, 14)
        pygame.draw.rect(self.canvas, theme.DANGER, card, width=2, border_radius=14)
        heading = "Reconnecting..." if client.reconnecting else "Connection lost"
        theme.text(self.canvas, heading, 26, theme.TEXT, (card.x + 32, card.y + 26), bold=True)
        attempt = client.reconnect_attempts
        detail = (f"Attempt {attempt}. Your seat is held for one minute."
                  if client.reconnecting else "Your seat is held for one minute.")
        theme.text(self.canvas, detail, 16, theme.MUTED, (card.x + 32, card.y + 74))
        theme.text(self.canvas, "Three reconnections per game, then a forfeit.", 14,
                   theme.MUTED, (card.x + 32, card.y + 104))

    def _route_tournament(self) -> None:
        if self.client is None:
            return
        snapshot = self.client.snapshot
        if not snapshot or snapshot.get("mode") != "tournament":
            return
        from .game_screen import GameScreen
        from .tournament_screen import TournamentScreen

        if snapshot.get("phase") == "playing":
            if not isinstance(self.screen, GameScreen):
                screen = GameScreen(self)
                screen.tournament_mode = True
                self.switch(screen)
        else:
            if not isinstance(self.screen, TournamentScreen):
                self.switch(TournamentScreen(self))

    # -------------------------------------------------------------------- loop
    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.screen.handle_event(self._map_event(event))
            self._route_tournament()
            self.screen.update(dt)
            self.screen.draw(self.canvas)

            self.toasts = [toast for toast in self.toasts if not toast.expired]
            for index, toast in enumerate(self.toasts):
                toast.draw(self.canvas, index)

            if self.client is not None:
                if not getattr(self.screen, "handles_errors", False):
                    errors = self.client.drain_errors()
                    for error in errors[:1]:
                        self.toast(error, "error")
                self._watch_connection()

            self._draw_connection_banner()
            self._present()
        self.leave_game()
        pygame.quit()
