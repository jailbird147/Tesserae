"""Smoke test: the About screen renders and the menu has the new button."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

pygame.init()
from tessera.ui.app import MenuScreen, AboutScreen


class FakeApp:
    def quit(self):
        pass

    def switch(self, screen):
        self.screen = screen
        self.screen.enter()


app = FakeApp()
menu = MenuScreen(app)
menu.enter()
assert len(menu.buttons) == 8, f"menu has {len(menu.buttons)} buttons, expected 8"
about = AboutScreen(app)
app.switch(about)
surface = pygame.Surface((1600, 900))
about.draw(surface)
pygame.image.save(surface, "shots/22_about.png")
print("about screen ok, menu buttons:", len(menu.buttons))