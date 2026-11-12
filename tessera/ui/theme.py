"""Colours, fonts and drawing helpers."""

from __future__ import annotations

import math
import pygame

# --------------------------------------------------------------------- palette
# Tessera colours: ink and cream, with gold, coral and sage accents.
BG = (14, 59, 62)          # ink
BG_DARK = (8, 42, 44)      # ink deep
PANEL = (11, 50, 53)
PANEL_SOFT = (18, 72, 75)
PANEL_HI = (27, 90, 86)
LINE = (44, 110, 99)
TEXT = (244, 235, 221)     # cream
MUTED = (127, 168, 156)    # sage
ACCENT = (201, 162, 39)    # gold
ACCENT_DARK = (143, 115, 24)
DANGER = (196, 85, 59)     # coral
SUCCESS = (122, 176, 144)
TILE = (251, 245, 233)
TILE_SHADE = (194, 174, 139)
TILE_TEXT = (14, 59, 62)
TILE_BLANK = (239, 227, 203)
BOARD_WOOD = (18, 72, 75)  # board surround (flat panel, not wood)
BOARD_INNER = (11, 50, 53)
SQUARE = (237, 226, 206)
PREMIUM_COLORS = {
    "TW": (196, 85, 59),
    "DW": (235, 213, 155),
    "TL": (143, 185, 168),
    "DL": (201, 222, 212),
}
PREMIUM_TEXT = {
    "TW": (251, 243, 228),
    "DW": (14, 59, 62),
    "TL": (14, 59, 62),
    "DL": (51, 86, 90),
}
GRID = (216, 202, 177)
SLATE = (107, 127, 128)

_fonts: dict[tuple[str, int, bool], pygame.font.Font] = {}


def font(size: int, bold: bool = False, name: str = "segoeui") -> pygame.font.Font:
    key = (name, size, bold)
    cached = _fonts.get(key)
    if cached is None:
        cached = pygame.font.SysFont(name, size, bold=bold)
        _fonts[key] = cached
    return cached


def tile_font(size: int) -> pygame.font.Font:
    return font(size, bold=True, name="georgia")


def title_font(size: int) -> pygame.font.Font:
    return font(size, bold=True, name="georgia")


# ------------------------------------------------------------------- primitives
def rounded_rect(surface, rect, color, radius=10, width=0):
    pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)


def panel(surface, rect, color=PANEL, radius=14, shadow=True):
    if shadow:
        shadow_rect = pygame.Rect(rect.x, rect.y + 3, rect.width, rect.height)
        rounded_rect(surface, shadow_rect, (5, 30, 32), radius)
    rounded_rect(surface, rect, color, radius)


def text(surface, value, size, color=TEXT, pos=(0, 0), anchor="topleft", bold=False, name="segoeui"):
    rendered = font(size, bold, name).render(str(value), True, color)
    rect = rendered.get_rect()
    setattr(rect, anchor, pos)
    surface.blit(rendered, rect)
    return rect


def heading(surface, value, size, pos, color=TEXT, anchor="topleft"):
    """Screen titles use the Georgia face, like the Tessera wordmark."""
    rendered = title_font(size).render(str(value), True, color)
    rect = rendered.get_rect()
    setattr(rect, anchor, pos)
    surface.blit(rendered, rect)
    return rect


def wrap_text(value: str, size: int, width: int, bold: bool = False, name: str = "segoeui") -> list[str]:
    f = font(size, bold, name)
    words = str(value).split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if f.size(candidate)[0] <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_tile(
    surface,
    rect: pygame.Rect,
    letter: str,
    value: int | None,
    *,
    blank: bool = False,
    selected: bool = False,
    ghost: bool = False,
    highlight: tuple[int, int, int] | None = None,
    small: bool = False,
    value_color: tuple[int, int, int] | None = None,
):
    body = TILE_BLANK if blank else TILE
    if ghost:
        body = (222, 212, 192)

    shadow = rect.move(0, 3)
    rounded_rect(surface, shadow, (106, 92, 68) if not ghost else (150, 140, 120), 7)

    if highlight:
        outer = rect.inflate(6, 6)
        rounded_rect(surface, outer, highlight, 9)
    rounded_rect(surface, rect, body, 7)
    pygame.draw.rect(surface, TILE_SHADE, rect, width=1, border_radius=7)

    label = letter.upper() if letter else ""
    if label:
        size = int(rect.height * (0.62 if not small else 0.5))
        rendered = tile_font(size).render(label, True, TILE_TEXT)
        pos = rendered.get_rect(center=(rect.centerx, rect.centery - rect.height * 0.04))
        surface.blit(rendered, pos)

    if value is not None:
        vfont = font(max(9, int(rect.height * 0.22)), True)
        vtext = vfont.render(str(value), True, value_color or SLATE)
        vrect = vtext.get_rect()
        vrect.bottomright = (rect.right - 5, rect.bottom - 3)
        surface.blit(vtext, vrect)


def draw_clock_bar(surface, rect, fraction: float, color: tuple[int, int, int]):
    rounded_rect(surface, rect, (5, 30, 32), 4)
    f = max(0.0, min(1.0, fraction))
    if f <= 0:
        return
    inner = pygame.Rect(rect.x, rect.y, int(rect.width * f), rect.height)
    rounded_rect(surface, inner, color, 4)


def format_clock(seconds: float) -> str:
    seconds = max(0, int(math.ceil(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


def vgradient(surface, rect, top, bottom):
    """Simple vertical gradient fill."""
    for i in range(rect.height):
        t = i / max(1, rect.height - 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
        pygame.draw.line(surface, color, (rect.x, rect.y + i), (rect.right, rect.y + i))


def soft_circle(surface, center, radius, color):
    """Cheap glow: concentric circles with low alpha."""
    layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for i in range(8, 0, -1):
        alpha = int(10 + (8 - i) * 3)
        pygame.draw.circle(layer, (*color, alpha), (radius, radius), int(radius * i / 8))
    surface.blit(layer, (center[0] - radius, center[1] - radius))
