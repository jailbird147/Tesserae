import os
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

pygame.init()
src = pygame.Surface((1240, 880))
src.fill((20, 60, 60))
pygame.draw.circle(src, (200, 160, 40), (600, 440), 200)
pygame.font.SysFont("georgia", 40).render("TESSERA", True, (250, 245, 230))

for target in ((1920, 1080), (1600, 1136), (2560, 1440)):
    start = time.perf_counter()
    for _ in range(30):
        scaled = pygame.transform.smoothscale(src, target)
    smooth = (time.perf_counter() - start) / 30
    start = time.perf_counter()
    for _ in range(30):
        scaled = pygame.transform.scale(src, target)
    nearest = (time.perf_counter() - start) / 30
    print(target, "smooth %.1f ms" % (smooth * 1000), "nearest %.1f ms" % (nearest * 1000))

# Can event positions be rewritten?
event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (10, 10), "button": 1})
try:
    event.pos = (5, 5)
    print("event.pos assignable", event.pos)
except Exception as exc:
    print("event.pos not assignable:", exc)
    clone = pygame.event.Event(event.type, {**event.dict, "pos": (7, 7)})
    print("clone ok", clone.pos)
