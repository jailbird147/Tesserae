"""Small UI widgets."""

from __future__ import annotations

import time

import pygame

from . import theme


class Button:
    def __init__(self, rect, label, on_click=None, *, style="secondary", size=19, enabled=True, tooltip=""):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.style = style
        self.size = size
        self.enabled = enabled
        self.tooltip = tooltip
        self.hover = False
        self.pressed = False

    def handle_event(self, event) -> bool:
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.pressed and self.rect.collidepoint(event.pos):
                self.pressed = False
                if self.on_click:
                    self.on_click()
                return True
            self.pressed = False
        return False

    def draw(self, surface):
        if self.style == "primary":
            base = theme.ACCENT if self.enabled else (110, 96, 60)
            edge = (220, 201, 142)
            fg = theme.PANEL if self.enabled else (60, 66, 60)
        elif self.style == "danger":
            base = theme.DANGER if self.enabled else (110, 74, 70)
            edge = (150, 60, 52)
            fg = theme.TEXT if self.enabled else (90, 82, 80)
        elif self.style == "ghost":
            base = (0, 0, 0, 0)
            edge = (0, 0, 0, 0)
            fg = theme.MUTED if not self.hover else theme.TEXT
        else:
            base = theme.PANEL_SOFT if not self.hover else theme.PANEL_HI
            edge = theme.LINE
            fg = theme.TEXT

        if not self.enabled:
            fg = (84, 101, 97)

        if self.style != "ghost":
            if self.pressed:
                base = tuple(max(0, c - 14) for c in base)
            shadow = self.rect.move(0, 3)
            theme.rounded_rect(surface, shadow, (5, 30, 32), 10)
            if self.enabled:
                theme.rounded_rect(surface, self.rect, base, 10)
                pygame.draw.rect(surface, edge, self.rect, width=1, border_radius=10)
            else:
                theme.rounded_rect(surface, self.rect, tuple(int(c * 0.40) for c in base), 10)
        theme.text(surface, self.label, self.size, fg, self.rect.center, "center", bold=True)


class TextInput:
    def __init__(self, rect, placeholder="", max_len=40, text_value=""):
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.value = text_value
        self.max_len = max_len
        self.focus = False
        self._caret = time.monotonic()

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focus = self.rect.collidepoint(event.pos)
            return self.focus
        if not self.focus:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
                return True
            if event.key == pygame.K_RETURN:
                return True
            if event.unicode and event.unicode.isprintable() and len(self.value) < self.max_len:
                self.value += event.unicode
                return True
        return False

    def draw(self, surface):
        color = theme.PANEL_HI if self.focus else theme.PANEL_SOFT
        theme.rounded_rect(surface, self.rect, color, 10)
        pygame.draw.rect(surface, theme.ACCENT if self.focus else theme.LINE, self.rect, width=1, border_radius=10)
        text_value = self.value or self.placeholder
        color_text = theme.TEXT if self.value else theme.MUTED
        theme.text(surface, text_value, 19, color_text, (self.rect.x + 14, self.rect.centery), "midleft")
        if self.focus and (time.monotonic() - self._caret) % 1.0 < 0.55:
            width = theme.font(19).size(self.value)[0]
            x = self.rect.x + 14 + width + 2
            pygame.draw.line(surface, theme.ACCENT, (x, self.rect.centery - 10), (x, self.rect.centery + 10), 2)


class Toggle:
    def __init__(self, rect, label, value=True, on_change=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.value = bool(value)
        self.on_change = on_change
        self.hover = False

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.value = not self.value
            if self.on_change:
                self.on_change(self.value)
            return True
        return False

    def draw(self, surface):
        switch = pygame.Rect(self.rect.right - 56, self.rect.centery - 13, 56, 26)
        theme.text(surface, self.label, 18, theme.TEXT, (self.rect.x, self.rect.centery), "midleft")
        theme.rounded_rect(surface, switch, theme.ACCENT if self.value else (52, 84, 74), 13)
        knob_x = switch.right - 13 if self.value else switch.left + 13
        pygame.draw.circle(surface, (250, 246, 232), (knob_x, switch.centery), 10)


class Stepper:
    def __init__(self, rect, label, options, index=0, on_change=None, format_value=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.options = list(options)
        self.index = index
        self.on_change = on_change
        self.format_value = format_value or (lambda value: str(value))

    @property
    def value(self):
        return self.options[self.index]

    def set_value(self, value):
        if value in self.options:
            self.index = self.options.index(value)
            if self.on_change:
                self.on_change(self.value)

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            left = pygame.Rect(self.rect.right - 90, self.rect.centery - 15, 30, 30)
            right = pygame.Rect(self.rect.right - 40, self.rect.centery - 15, 30, 30)
            if left.collidepoint(event.pos):
                self.index = (self.index - 1) % len(self.options)
                if self.on_change:
                    self.on_change(self.value)
                return True
            if right.collidepoint(event.pos):
                self.index = (self.index + 1) % len(self.options)
                if self.on_change:
                    self.on_change(self.value)
                return True
        return False

    def draw(self, surface):
        theme.text(surface, self.label, 18, theme.MUTED, (self.rect.x, self.rect.centery), "midleft")
        theme.text(surface, self.format_value(self.value), 19, theme.TEXT, (self.rect.right - 118, self.rect.centery), "midright", bold=True)
        for x, glyph in ((self.rect.right - 90, "-"), (self.rect.right - 40, "+")):
            box = pygame.Rect(x, self.rect.centery - 15, 30, 30)
            theme.rounded_rect(surface, box, theme.PANEL_SOFT, 8)
            theme.text(surface, glyph, 20, theme.TEXT, box.center, "center", bold=True)


class Toast:
    def __init__(self, message, kind="info", ttl=2.6):
        self.message = message
        self.kind = kind
        self.created = time.monotonic()
        self.ttl = ttl

    @property
    def expired(self):
        return time.monotonic() - self.created > self.ttl

    def draw(self, surface, index=0):
        colors = {
            "info": theme.PANEL_HI,
            "error": theme.DANGER,
            "success": (52, 122, 88),
        }
        color = colors.get(self.kind, theme.PANEL_HI)
        width = theme.font(17).size(self.message)[0] + 40
        rect = pygame.Rect(0, 0, min(560, width), 44)
        rect.midtop = (surface.get_width() // 2, 100 + index * 52)
        theme.rounded_rect(surface, rect.move(0, 3), (8, 20, 16), 10)
        theme.rounded_rect(surface, rect, color, 10)
        theme.text(surface, self.message, 17, theme.TEXT, rect.center, "center")
