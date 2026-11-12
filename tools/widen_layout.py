"""One-off: widen the fixed layouts from 1240x880 to 1600x900."""

import io
import os

ROOT = r"F:\Tessera"
APP = os.path.join(ROOT, "tessera", "ui", "app.py")
SETTINGS = os.path.join(ROOT, "tessera", "ui", "settings_screen.py")
ANALYSIS = os.path.join(ROOT, "tessera", "ui", "analysis_screen.py")

APP_EDITS = [
    # How to play
    ('draw_background(surface, "How to play", "A quick reminder of the rules")',
     'draw_background(surface, "How to play", "A quick reminder of the rules", left=240)'),
    ('theme.text(surface, title, 21, theme.ACCENT, (60, y), bold=True)',
     'theme.text(surface, title, 21, theme.ACCENT, (240, y), bold=True)'),
    ('theme.text(surface, line, 19, theme.TEXT, (250, y + i * 26))',
     'theme.text(surface, line, 19, theme.TEXT, (430, y + i * 26))'),
    ('self.back = Button((60, 760, 160, 48), "Back"',
     'self.back = Button((240, 760, 160, 48), "Back"'),
    # Local setup
    ('TextInput((280, 190, 440, 46)', 'TextInput((470, 190, 440, 46)'),
    ('Stepper((280, 258, 440, 40)', 'Stepper((470, 258, 440, 40)'),
    ('Stepper((280, 318 + i * 64, 440, 40)', 'Stepper((470, 318 + i * 64, 440, 40)'),
    ('Stepper((280, 526, 440, 40)', 'Stepper((470, 526, 440, 40)'),
    ('Toggle((280, 574, 440, 40)', 'Toggle((470, 574, 440, 40)'),
    ('Stepper((280, 622, 440, 40)', 'Stepper((470, 622, 440, 40)'),
    ('Button((280, 676, 250, 54)', 'Button((470, 676, 250, 54)'),
    ('Button((546, 676, 154, 54)', 'Button((736, 676, 154, 54)'),
    ('draw_background(surface, "Play against the computer", "Set the table, then start")',
     'draw_background(surface, "Play against the computer", "Set the table, then start", left=440)'),
    ('pygame.Rect(250, 150, 720, 600)', 'pygame.Rect(440, 150, 720, 600)'),
    ('theme.text(surface, "Name", 17, theme.MUTED, (280, 168))',
     'theme.text(surface, "Name", 17, theme.MUTED, (470, 168))'),
    ('theme.text(surface, info["blurb"], 14, theme.MUTED, (280, 360 + i * 64))',
     'theme.text(surface, info["blurb"], 14, theme.MUTED, (470, 360 + i * 64))'),
    ('theme.text(surface, self.error, 16, theme.DANGER, (280, 736))',
     'theme.text(surface, self.error, 16, theme.DANGER, (470, 736))'),
    # Host setup
    ('TextInput((300, 190, 420, 46)', 'TextInput((510, 190, 420, 46)'),
    ('Stepper((300, 258, 420, 40)', 'Stepper((510, 258, 420, 40)'),
    ('Stepper((300, 312, 420, 40)', 'Stepper((510, 312, 420, 40)'),
    ('Toggle((300, 358, 420, 40)', 'Toggle((510, 358, 420, 40)'),
    ('Stepper((300, 402, 420, 40)', 'Stepper((510, 402, 420, 40)'),
    ('TextInput((300, 476, 200, 46)', 'TextInput((510, 476, 200, 46)'),
    ('Button((300, 548, 250, 56)', 'Button((510, 548, 250, 56)'),
    ('Button((566, 548, 154, 56)', 'Button((776, 548, 154, 56)'),
    ('draw_background(surface, "Host an online game", "Your PC becomes the game server")',
     'draw_background(surface, "Host an online game", "Your PC becomes the game server", left=490)'),
    ('pygame.Rect(280, 165, 620, 470)', 'pygame.Rect(490, 165, 620, 470)'),
    ('theme.text(surface, "Name", 17, theme.MUTED, (300, 168))',
     'theme.text(surface, "Name", 17, theme.MUTED, (510, 168))'),
    ('theme.text(surface, "Port", 17, theme.MUTED, (300, 454))',
     'theme.text(surface, "Port", 17, theme.MUTED, (510, 454))'),
    ('theme.MUTED, (520, 489))', 'theme.MUTED, (730, 489))'),
    ('theme.text(surface, self.error, 16, theme.DANGER, (300, 612))',
     'theme.text(surface, self.error, 16, theme.DANGER, (510, 612))'),
    # Join
    ('TextInput((300, 250, 420, 46)', 'TextInput((585, 250, 420, 46)'),
    ('TextInput((300, 336, 420, 46)', 'TextInput((585, 336, 420, 46)'),
    ('Button((300, 414, 140, 56)', 'Button((585, 414, 140, 56)'),
    ('Button((452, 414, 140, 56)', 'Button((737, 414, 140, 56)'),
    ('Button((604, 414, 120, 56)', 'Button((889, 414, 120, 56)'),
    ('draw_background(surface, "Join an online game", "Ask the host for their address")',
     'draw_background(surface, "Join an online game", "Ask the host for their address", left=565)'),
    ('pygame.Rect(280, 200, 470, 350)', 'pygame.Rect(565, 200, 470, 350)'),
    ('theme.text(surface, "Server address", 17, theme.MUTED, (300, 218))',
     'theme.text(surface, "Server address", 17, theme.MUTED, (585, 218))'),
    ('theme.text(surface, "Name", 17, theme.MUTED, (300, 306))',
     'theme.text(surface, "Name", 17, theme.MUTED, (585, 306))'),
    ('theme.MUTED, (300, 480))', 'theme.MUTED, (585, 480))'),
    ('theme.text(surface, self.error, 16, theme.DANGER, (300, 506))',
     'theme.text(surface, self.error, 16, theme.DANGER, (585, 506))'),
    # Lobby
    ('Button((300, 756, 240, 54)', 'Button((440, 756, 240, 54)'),
    ('Button((560, 756, 140, 54)', 'Button((700, 756, 140, 54)'),
    ('Button((716, 756, 150, 54)', 'Button((856, 756, 150, 54)'),
    ('Stepper((88, 590, 420, 36)', 'Stepper((228, 590, 420, 36)'),
    ('Stepper((88, 630, 420, 36)', 'Stepper((228, 630, 420, 36)'),
    ('Stepper((88, 670, 420, 36)', 'Stepper((228, 670, 420, 36)'),
    ('draw_background(surface, "Lobby", "Waiting for players")',
     'draw_background(surface, "Lobby", "Waiting for players", left=200)'),
    ('theme.text(surface, "Connecting...", 22, theme.TEXT, (60, 200))',
     'theme.text(surface, "Connecting...", 22, theme.TEXT, (200, 200))'),
    ('pygame.Rect(60, 140, 640, 600)', 'pygame.Rect(200, 140, 640, 600)'),
    ('theme.text(surface, "Server address", 16, theme.MUTED, (88, 162))',
     'theme.text(surface, "Server address", 16, theme.MUTED, (228, 162))'),
    ('theme.text(surface, address or "starting...", 26, theme.ACCENT, (88, 186), bold=True)',
     'theme.text(surface, address or "starting...", 26, theme.ACCENT, (228, 186), bold=True)'),
    ('theme.text(surface, line, 15, theme.MUTED, (88, 224 + i * 20))',
     'theme.text(surface, line, 15, theme.MUTED, (228, 224 + i * 20))'),
    ('theme.text(surface, f"Public IP: {self.public}", 15, theme.MUTED, (88, 266))',
     'theme.text(surface, f"Public IP: {self.public}", 15, theme.MUTED, (228, 266))'),
    ('theme.text(surface, "Players", 17, theme.MUTED, (88, 300))',
     'theme.text(surface, "Players", 17, theme.MUTED, (228, 300))'),
    ('theme.ACCENT, (640, 304), "topright")', 'theme.ACCENT, (780, 304), "topright")'),
    ('rect = pygame.Rect(88, y, 584, 50)', 'rect = pygame.Rect(228, y, 584, 50)'),
    ('theme.SUCCESS, (300, 700))', 'theme.SUCCESS, (440, 700))'),
    ('theme.MUTED, (300, 820))', 'theme.MUTED, (440, 820))'),
    ('theme.MUTED, (300, 748))', 'theme.MUTED, (440, 748))'),
    ('theme.TEXT, (300, 776))', 'theme.TEXT, (440, 776))'),
    # Results
    ('Button((240, 700, 200, 54)', 'Button((420, 700, 200, 54)'),
    ('Button((456, 700, 220, 54)', 'Button((636, 700, 220, 54)'),
    ('Button((692, 700, 180, 54)', 'Button((872, 700, 180, 54)'),
    ('draw_background(surface, "Final scores", "")',
     'draw_background(surface, "Final scores", "", left=240)'),
    ('theme.text(surface, state.get("result", ""), 22, theme.ACCENT, (60, 140), bold=True)',
     'theme.text(surface, state.get("result", ""), 22, theme.ACCENT, (240, 140), bold=True)'),
    ('rect = pygame.Rect(60, y, 760, 76)', 'rect = pygame.Rect(240, y, 1000, 76)'),
    ('theme.MUTED, (240, 766))', 'theme.MUTED, (420, 766))'),
]

SETTINGS_EDITS = [
    ('theme.heading(surface, "Settings", 46, (60, 44))', 'theme.heading(surface, "Settings", 46, (180, 44))'),
    ('theme.text(surface, "Your own preferences, and the rules the host controls", 18, theme.MUTED, (62, 100))',
     'theme.text(surface, "Your own preferences, and the rules the host controls", 18, theme.MUTED, (182, 100))'),
    ('left = pygame.Rect(60, 140, 520, 620)', 'left = pygame.Rect(180, 140, 620, 620)'),
    ('right = pygame.Rect(620, 140, 560, 620)', 'right = pygame.Rect(840, 140, 620, 620)'),
    ('TextInput((88, 246, 440, 44)', 'TextInput((208, 246, 520, 44)'),
    ('Toggle((88, 326, 440, 40)', 'Toggle((208, 326, 520, 40)'),
    ('Toggle((88, 372, 440, 40)', 'Toggle((208, 372, 520, 40)'),
    ('Toggle((88, 418, 440, 40)', 'Toggle((208, 418, 520, 40)'),
    ('TextInput((88, 508, 200, 44)', 'TextInput((208, 508, 200, 44)'),
    ('Stepper((648, 210, 440, 40)', 'Stepper((868, 210, 520, 40)'),
    ('Stepper((648, 262, 440, 40)', 'Stepper((868, 262, 520, 40)'),
    ('Stepper((648, 314, 440, 40)', 'Stepper((868, 314, 520, 40)'),
    ('Toggle((648, 366, 440, 40)', 'Toggle((868, 366, 520, 40)'),
    ('Toggle((648, 412, 440, 40)', 'Toggle((868, 412, 520, 40)'),
    ('Toggle((648, 458, 440, 40)', 'Toggle((868, 458, 520, 40)'),
    ('Toggle((648, 504, 440, 40)', 'Toggle((868, 504, 520, 40)'),
    ('Button((88, 790, 170, 48)', 'Button((208, 790, 170, 48)'),
    ('theme.text(surface, "Name", 16, theme.MUTED, (88, 224))',
     'theme.text(surface, "Name", 16, theme.MUTED, (208, 224))'),
    ('theme.text(surface, "Default port for hosting", 16, theme.MUTED, (88, 486))',
     'theme.text(surface, "Default port for hosting", 16, theme.MUTED, (208, 486))'),
    ('pygame.Rect(88, 566, 440, 112)', 'pygame.Rect(208, 566, 520, 112)'),
    ('theme.MUTED, (648, 560))', 'theme.MUTED, (868, 560))'),
    ('theme.text(surface, label, 15, theme.MUTED, (648, y + 18), "midleft")',
     'theme.text(surface, label, 15, theme.MUTED, (868, y + 18), "midleft")'),
    ('theme.text(surface, value, 17, theme.TEXT, (1064, y + 18), "midright", bold=True)',
     'theme.text(surface, value, 17, theme.TEXT, (1436, y + 18), "midright", bold=True)'),
]

ANALYSIS_EDITS = [
    ('theme.heading(surface, "Game analysis", 46, (60, 36))', 'theme.heading(surface, "Game analysis", 46, (240, 36))'),
    ('theme.text(surface, "Quackle equity: points, leave value and board position", 18, theme.MUTED, (62, 92))',
     'theme.text(surface, "Quackle equity: points, leave value and board position", 18, theme.MUTED, (242, 92))'),
    ('card = pygame.Rect(60, 130, 1120, 100)', 'card = pygame.Rect(240, 130, 1120, 100)'),
    ('table = pygame.Rect(60, 240, 1120, 520)', 'table = pygame.Rect(240, 240, 1120, 520)'),
    ('theme.text(surface, "Starting analysis...", 22, theme.TEXT, (60, 180))',
     'theme.text(surface, "Starting analysis...", 22, theme.TEXT, (240, 180))'),
    ('theme.text(surface, analysis.get("message", "Analysis failed."), 20, theme.DANGER, (60, 180))',
     'theme.text(surface, analysis.get("message", "Analysis failed."), 20, theme.DANGER, (240, 180))'),
    ('theme.text(surface, f"Analysing move {done} of {total}...", 24, theme.TEXT, (60, 180), bold=True)',
     'theme.text(surface, f"Analysing move {done} of {total}...", 24, theme.TEXT, (240, 180), bold=True)'),
    ('bar = pygame.Rect(60, 220, 800, 12)', 'bar = pygame.Rect(240, 220, 800, 12)'),
    ('16, theme.MUTED, (60, 252))', '16, theme.MUTED, (240, 252))'),
    ('Button((60, 800, 170, 48)', 'Button((240, 800, 170, 48)'),
]


def apply(path, edits):
    text = io.open(path, encoding="utf-8").read()
    for old, new in edits:
        count = text.count(old)
        if count != 1:
            print(f"  !! {count} matches for: {old[:70]}")
            continue
        text = text.replace(old, new)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)
    print("updated", os.path.basename(path))


apply(APP, APP_EDITS)
apply(SETTINGS, SETTINGS_EDITS)
apply(ANALYSIS, ANALYSIS_EDITS)
print("done")
