"""Settings: personal preferences plus the host's match rules."""

from __future__ import annotations

import pygame

from ..lexicon import (
    delete_wordlist,
    import_wordlist,
    lexicon_identity,
    lexicon_label,
    lexicon_names,
    resolve as resolve_lexicon,
)
from . import theme
from .widgets import Button, Stepper, TextInput, Toggle

LEXICON_RECT = (868, 262, 520, 40)

TURN_CHOICES = [60, 90, 120, 180]


def _minutes(value: int) -> str:
    return f"{value // 60} min" if value % 60 == 0 else f"{value / 60:.1f} min"


class SettingsScreen:
    def __init__(self, app, back_target=None) -> None:
        self.app = app
        self.back_target = back_target
        self.name_input = None
        self.port_input = None
        self.widgets = []
        self.clocks = None
        self.lexicon = None
        self.minimum = None
        self.bingo = None
        self.six_pass = None
        self.recycle = None
        self.hints = None
        self.fullscreen = None
        self.highlight = None
        self.coordinates = None
        self._build()

    # ------------------------------------------------------------------ state
    def _snapshot(self):
        return self.app.client.snapshot if self.app.client else None

    def _live_lobby(self) -> bool:
        snapshot = self._snapshot()
        return bool(snapshot and snapshot.get("phase") == "lobby")

    def _host(self) -> bool:
        return bool(self.app.client and self.app.client.is_host)

    def _rules_editable(self) -> bool:
        if self.app.client is None:
            return True  # no game: these act as defaults for the next game
        return self._live_lobby() and self._host()

    def _rules_source(self) -> dict:
        snapshot = self._snapshot()
        if snapshot:
            settings = snapshot.get("settings", {})
        else:
            settings = self.app.settings
        return {
            "turn_seconds": settings.get("turn_seconds", 120),
            "lexicon": settings.get("lexicon", "csw"),
            "allow_blank_recycle": settings.get("allow_blank_recycle", True),
            "allow_hints": settings.get("allow_hints", True),
            "bingo_bonus": settings.get("bingo_bonus", True),
            "end_after_six_scoreless": settings.get("end_after_six_scoreless", True),
            "minimum_word_length": settings.get("minimum_word_length", 0),
        }

    def enter(self) -> None:
        pass

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        self.name_input = TextInput((208, 246, 520, 44), "Your name", 18, self.app.settings.get("name", "Player"))
        self.fullscreen = Toggle((208, 326, 520, 40), "Full screen",
                                 bool(self.app.settings.get("fullscreen", False)), self._fullscreen_changed)
        self.highlight = Toggle((208, 372, 520, 40), "Highlight the last move",
                                bool(self.app.settings.get("highlight_last_move", True)), self._highlight_changed)
        self.coordinates = Toggle((208, 418, 520, 40), "Show A-O / 1-15 coordinates",
                                  bool(self.app.settings.get("show_coordinates", True)), self._coordinates_changed)
        self.port_input = TextInput((208, 508, 200, 44), "Port", 5, str(self.app.settings.get("port", "5467")))

        rules = self._rules_source()
        editable = self._rules_editable()
        self.clocks = Stepper((868, 210, 520, 40), "Clock per turn", TURN_CHOICES,
                              TURN_CHOICES.index(rules["turn_seconds"]) if rules["turn_seconds"] in TURN_CHOICES else 2,
                              self._clock_changed, format_value=_minutes)
        from .app import make_lexicon_stepper
        self.lexicon = make_lexicon_stepper(LEXICON_RECT, rules["lexicon"], self._lexicon_changed)
        self.import_button = Button((208, 690, 232, 40), "Import a word list", self._import_clicked, size=15)
        self.remove_button = Button((452, 690, 150, 40), "Remove list", self._remove_clicked, size=15)
        self.list_status = ""
        self.minimum = Stepper((868, 314, 520, 40), "Shortest word", [0, 3, 4, 5],
                               [0, 3, 4, 5].index(rules["minimum_word_length"]) if rules["minimum_word_length"] in (0, 3, 4, 5) else 0,
                               self._minimum_changed,
                               format_value=lambda v: "any" if not v else f"{v}+")
        self.bingo = Toggle((868, 366, 520, 40), "Bingo bonus (+50 for seven)",
                            bool(rules["bingo_bonus"]), self._bingo_changed)
        self.six_pass = Toggle((868, 412, 520, 40), "End after six scoreless turns",
                               bool(rules["end_after_six_scoreless"]), self._six_pass_changed)
        self.recycle = Toggle((868, 458, 520, 40), "One blank recycle per player",
                              bool(rules["allow_blank_recycle"]), self._recycle_changed)
        self.hints = Toggle((868, 504, 520, 40), "Hints allowed", bool(rules["allow_hints"]), self._hints_changed)
        for widget in (self.clocks, self.lexicon, self.minimum, self.bingo, self.six_pass, self.recycle, self.hints):
            widget.enabled = editable

        self.widgets = [self.name_input, self.fullscreen, self.highlight, self.coordinates, self.port_input,
                        self.import_button, self.remove_button,
                        self.clocks, self.lexicon, self.minimum, self.bingo, self.six_pass,
                        self.recycle, self.hints]
        self._refresh_list_buttons()
        self.back = Button((208, 790, 170, 48), "Back", self.go_back)

    # --------------------------------------------------------------- handlers
    def _save(self) -> None:
        from .app import save_settings
        save_settings(self.app.settings)

    def _fullscreen_changed(self, value: bool) -> None:
        self.app.settings["fullscreen"] = bool(value)
        self._save()
        self.app.apply_display_preferences()

    def _highlight_changed(self, value: bool) -> None:
        self.app.settings["highlight_last_move"] = bool(value)
        self._save()

    def _coordinates_changed(self, value: bool) -> None:
        self.app.settings["show_coordinates"] = bool(value)
        self._save()

    def _push_rule(self, **payload) -> None:
        if self._live_lobby() and self._host():
            self.app.client.host_command(action="settings", **payload)

    def _clock_changed(self, value: int) -> None:
        self.app.settings["turn_seconds"] = value
        self._save()
        self._push_rule(turn_seconds=value)

    def _lexicon_changed(self, value: str) -> None:
        self.app.settings["lexicon"] = value
        self.list_status = ""
        self._save()
        self._push_rule(lexicon=value)
        self._refresh_list_buttons()

    def _refresh_list_buttons(self) -> None:
        identity = lexicon_identity(self.lexicon.value if self.lexicon else None)
        self.remove_button.enabled = bool(identity.get("custom")) and self._rules_editable()

    def _import_clicked(self) -> None:
        from .filedialog import open_word_list

        path = open_word_list()
        if not path:
            return
        try:
            identity = import_wordlist(path)
        except (ValueError, OSError) as exc:
            self.list_status = str(exc)
            return
        self.list_status = f"Added {identity['label']} · {identity['words']:,} words"
        self._rebuild_lexicon(identity["name"])

    def _remove_clicked(self) -> None:
        name = self.lexicon.value if self.lexicon else ""
        identity = lexicon_identity(name)
        if not identity.get("custom"):
            return
        if delete_wordlist(name):
            self.list_status = f"Removed {identity['label']}"
            self._rebuild_lexicon(resolve_lexicon(None))

    def _rebuild_lexicon(self, name: str) -> None:
        """Swap in a fresh chooser after a list is added or removed."""
        from .app import make_lexicon_stepper

        self.app.settings["lexicon"] = resolve_lexicon(name)
        self._save()
        self._push_rule(lexicon=self.app.settings["lexicon"])
        index = self.widgets.index(self.lexicon) if self.lexicon in self.widgets else None
        self.lexicon = make_lexicon_stepper(LEXICON_RECT, self.app.settings["lexicon"], self._lexicon_changed)
        self.lexicon.enabled = self._rules_editable()
        if index is not None:
            self.widgets[index] = self.lexicon
        self._refresh_list_buttons()

    def _minimum_changed(self, value: int) -> None:
        self.app.settings["minimum_word_length"] = value
        self._save()
        self._push_rule(minimum_word_length=value)

    def _bingo_changed(self, value: bool) -> None:
        self.app.settings["bingo_bonus"] = bool(value)
        self._save()
        self._push_rule(bingo_bonus=bool(value))

    def _six_pass_changed(self, value: bool) -> None:
        self.app.settings["end_after_six_scoreless"] = bool(value)
        self._save()
        self._push_rule(end_after_six_scoreless=bool(value))

    def _recycle_changed(self, value: bool) -> None:
        self.app.settings["allow_blank_recycle"] = bool(value)
        self._save()
        self._push_rule(allow_blank_recycle=bool(value))

    def _hints_changed(self, value: bool) -> None:
        self.app.settings["allow_hints"] = bool(value)
        self._save()
        self._push_rule(allow_hints=bool(value))

    def go_back(self) -> None:
        if self.name_input.value.strip():
            self.app.settings["name"] = self.name_input.value.strip()[:18]
        if self.port_input.value.strip().isdigit():
            self.app.settings["port"] = self.port_input.value.strip()
        self._save()
        if self.back_target is not None:
            self.app.switch(self.back_target)
        else:
            from .app import MenuScreen
            self.app.switch(MenuScreen(self.app))

    # ---------------------------------------------------------------- events
    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.go_back()
            return
        self.back.handle_event(event)
        for widget in self.widgets:
            if getattr(widget, "enabled", True) and widget.handle_event(event):
                return

    def update(self, dt: float) -> None:
        pass

    # ------------------------------------------------------------------ draw
    def draw(self, surface) -> None:
        surface.fill(theme.BG_DARK)
        theme.vgradient(surface, pygame.Rect(0, 0, *surface.get_size()), (18, 72, 75), theme.BG_DARK)
        theme.heading(surface, "Settings", 46, (180, 44))
        theme.text(surface, "Your own preferences, and the rules the host controls", 18, theme.MUTED, (182, 100))

        left = pygame.Rect(180, 140, 620, 620)
        theme.panel(surface, left)
        theme.text(surface, "This computer", 22, theme.TEXT, (left.x + 28, left.y + 22), bold=True)
        theme.text(surface, "Saved for every game you start.", 15, theme.MUTED, (left.x + 28, left.y + 54))

        theme.text(surface, "Name", 16, theme.MUTED, (208, 224))
        self.name_input.draw(surface)
        self.fullscreen.draw(surface)
        self.highlight.draw(surface)
        self.coordinates.draw(surface)
        theme.text(surface, "Default port for hosting", 16, theme.MUTED, (208, 486))
        self.port_input.draw(surface)
        self._draw_dictionary(surface, pygame.Rect(208, 566, 520, 112), self._rules_source()["lexicon"])
        self.import_button.draw(surface)
        self.remove_button.draw(surface)
        if self.list_status:
            theme.text(surface, self.list_status, 13, theme.TEXT, (208, 740))

        right = pygame.Rect(840, 140, 620, 620)
        theme.panel(surface, right)
        theme.text(surface, "Match rules", 22, theme.TEXT, (right.x + 28, right.y + 22), bold=True)
        note = "Only the host can change these."
        if self.app.client is None:
            note = "Defaults for the next game you host or start."
        elif self._live_lobby() and self._host():
            note = "Everyone in the lobby sees these changes."
        elif not self._live_lobby():
            note = "Locked while a match is running."
        theme.text(surface, note, 15, theme.MUTED, (right.x + 28, right.y + 54))

        if self._rules_editable():
            self.clocks.draw(surface)
            self.lexicon.draw(surface)
            self.minimum.draw(surface)
            self.bingo.draw(surface)
            self.six_pass.draw(surface)
            self.recycle.draw(surface)
            self.hints.draw(surface)
            theme.text(surface, "Hints off disables the Hint button for everyone.", 13, theme.MUTED, (868, 560))
        else:
            rules = self._rules_source()
            rows = [
                ("Clock per turn", _minutes(rules["turn_seconds"])),
                ("Word list", lexicon_label(rules["lexicon"])),
                ("Shortest word", "any" if not rules["minimum_word_length"] else f"{rules['minimum_word_length']}+"),
                ("Bingo bonus", "+50" if rules["bingo_bonus"] else "off"),
                ("Six scoreless turns", "ends the game" if rules["end_after_six_scoreless"] else "no limit"),
                ("Blank recycle", "once per player" if rules["allow_blank_recycle"] else "off"),
                ("Hints", "allowed" if rules["allow_hints"] else "off"),
            ]
            for index, (label, value) in enumerate(rows):
                y = 206 + index * 46
                theme.text(surface, label, 15, theme.MUTED, (868, y + 18), "midleft")
                theme.text(surface, value, 17, theme.TEXT, (1436, y + 18), "midright", bold=True)

        self.back.draw(surface)

    def _draw_dictionary(self, surface, rect, name: str) -> None:
        identity = lexicon_identity(name)
        theme.rounded_rect(surface, rect, theme.PANEL_SOFT, 8)
        theme.text(surface, "WORD LIST", 11, theme.MUTED, (rect.x + 14, rect.y + 10), bold=True)
        theme.text(surface, f"{identity['label']} · {identity['words']:,} words", 17, theme.TEXT,
                   (rect.x + 14, rect.y + 30), bold=True)

        if identity["verified"]:
            badge_color, label, width = (28, 100, 89), "VERIFIED", 92
        elif identity.get("custom"):
            badge_color, label, width = (120, 96, 30), "CUSTOM LIST", 106
        else:
            badge_color, label, width = (54, 82, 96), "BUILT IN", 82
        badge = pygame.Rect(0, 0, width, 22)
        badge.topright = (rect.right - 14, rect.y + 20)
        theme.rounded_rect(surface, badge, badge_color, 11)
        theme.text(surface, label, 10, theme.TEXT, badge.center, "center", bold=True)

        digest = identity["sha256"]
        short = f"{digest[:10]}…{digest[-10:]}" if len(digest) > 24 else digest
        theme.text(surface, f"sha256 {short}", 11, theme.MUTED, (rect.x + 14, rect.y + 62))
        theme.text(surface, identity["file"], 11, theme.MUTED, (rect.x + 14, rect.y + 82))
