"""Render screens to PNGs without opening a window (for layout checks)."""

import os
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["TESSERA_HEADLESS"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from tessera.engine import shared_engine
from tessera.ui.app import App, HostSetupScreen, LocalSetupScreen, MenuScreen, JoinScreen, HowToScreen
from tessera.ui.settings_screen import SettingsScreen
from tessera.ui.analysis_screen import AnalysisScreen
from tessera.ui.game_screen import GameScreen

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shots")
os.makedirs(OUT, exist_ok=True)


def save(app, name):
    app.screen.update(0.016)
    app.screen.draw(app.surface)
    path = os.path.join(OUT, name)
    pygame.image.save(app.surface, path)
    print("saved", path)


def main():
    app = App()
    app.screen = MenuScreen(app)
    app.screen.enter()
    save(app, "01_menu.png")

    app.screen = LocalSetupScreen(app)
    app.screen.enter()
    save(app, "02_local_setup.png")

    app.screen = HostSetupScreen(app)
    app.screen.enter()
    save(app, "03_host_setup.png")

    app.screen = JoinScreen(app)
    app.screen.enter()
    save(app, "04_join.png")

    app.screen = HowToScreen(app)
    app.screen.enter()
    save(app, "11_howto.png")

    app.screen = SettingsScreen(app)
    app.screen.enter()
    save(app, "12_settings.png")

    app.start_local("You", [4], 120, True)
    time.sleep(0.5)
    save(app, "05_game_empty.png")

    # Play a few turns by hand using the engine so the board looks alive.
    engine = shared_engine()
    engine.ensure_started()
    for _ in range(24):
        snapshot = app.client.snapshot
        if not snapshot or not snapshot.get("state"):
            time.sleep(0.2)
            continue
        state = snapshot["state"]
        if state.get("game_over") or state["turn"] > 10:
            break
        if state.get("current") == app.client.seat:
            rack = state["players"][app.client.seat]["rack"]
            moves = engine.moves("".join(
                ("." if cell is None else (cell[0].lower() if cell[1] else cell[0]))
                for row in state["board"] for cell in row
            ), rack, "?" * 0, 0, 0, level=3, seconds=2, top=1)
            if moves:
                app.client.play(moves[0].placements)
            else:
                app.client.pass_turn()
        time.sleep(0.6)
    time.sleep(1.0)
    if isinstance(app.screen, GameScreen):
        save(app, "06_game_mid.png")

        # Ten-second warning: hold the time left at eight seconds and wait for
        # the red phase of the flash.
        app.screen.remaining_at = 8.0
        app.screen.snapshot_at = time.monotonic()
        while (time.monotonic() * 2.2) % 1.0 > 0.35:
            time.sleep(0.01)
        app.screen.draw(app.surface)
        pygame.image.save(app.surface, os.path.join(OUT, "15_low_clock.png"))
        print("saved", os.path.join(OUT, "15_low_clock.png"))
        app.screen.hints = [
            {"word": "QUARTZ", "score": 68, "cells": []},
            {"word": "QAT", "score": 31, "cells": []},
            {"word": "ZOA", "score": 24, "cells": []},
        ]
        save(app, "08_game_hints.png")
        app.screen.modal = "blank"
        app.screen.blank_square = (7, 7)
        save(app, "09_blank_modal.png")
        app.screen.modal = None
        app.screen.ask_yield()
        save(app, "10_yield_modal.png")

        # Reconnection banner: the link has dropped and the client is retrying.
        app.screen.modal = None
        if app.client is not None:
            app.client.connected = False
            app.client.reconnecting = True
            app.client.reconnect_attempts = 2
            app.screen.draw(app.surface)
            app._draw_connection_banner()
            pygame.image.save(app.surface, os.path.join(OUT, "21_reconnect.png"))
            print("saved", os.path.join(OUT, "21_reconnect.png"))
            app.client.connected = True
            app.client.reconnecting = False

        rows = [
            {"turn": 1, "played": "RIVAGES", "played_score": 74, "best": "RIVAGES", "best_score": 74, "loss": 0.0, "verdict": "Best"},
            {"turn": 3, "played": "ZONER", "played_score": 38, "best": "ZONER", "best_score": 38, "loss": 1.2, "verdict": "Good"},
            {"turn": 5, "played": "TIER", "played_score": 12, "best": "TRIER", "best_score": 27, "loss": 7.4, "verdict": "Inaccuracy"},
            {"turn": 7, "played": "DUX", "played_score": 19, "best": "DUX", "best_score": 19, "loss": 0.0, "verdict": "Best"},
            {"turn": 9, "played": "OWES", "played_score": 16, "best": "WOOFS", "best_score": 34, "loss": 13.6, "verdict": "Mistake"},
            {"turn": 11, "played": "QI", "played_score": 22, "best": "QINDAR", "best_score": 62, "loss": 41.9, "verdict": "Blunder"},
            {"turn": 13, "played": "BOWLED", "played_score": 29, "best": "BOWLED", "best_score": 29, "loss": 0.4, "verdict": "Best"},
            {"turn": 15, "played": "VISIER", "played_score": 31, "best": "VIREOS", "best_score": 36, "loss": 2.9, "verdict": "Good"},
        ]
        sample = {
            "type": "analysis", "phase": "done",
            "data": {
                "seat": 0, "name": "You", "moves": rows,
                "summary": {"count": len(rows), "average_loss": 8.7, "rating": "1400-1550",
                            "best": 3, "good": 2, "inaccuracy": 1, "mistake": 1, "blunder": 1},
            },
        }
        if app.client:
            app.client.analysis = sample
            app.screen = AnalysisScreen(app, back_target=app.screen)
            save(app, "13_analysis.png")
            app.screen._hover_pos = (1184, 296)
            save(app, "16_analysis_help.png")

        # Spectator view: a second client that only watches.
        if app.server is not None and app.client is not None:
            from tessera.net.client import NetClient
            watcher = NetClient()
            if watcher.connect("127.0.0.1", app.server.port, "Watcher", observe=True):
                app.client.close()
                app.client = watcher
                app.screen = GameScreen(app)
                time.sleep(1.0)
                save(app, "14_spectator.png")
    app.leave_game()
    time.sleep(0.2)

    app.host_game("Host", 3, 120, True, 0)
    time.sleep(1.0)
    save(app, "07_lobby.png")
    app.leave_game()
    time.sleep(0.2)

    # Tournament screens
    from tessera.ui.tournament_screen import TournamentSetupScreen
    app.screen = TournamentSetupScreen(app)
    save(app, "17_tournament_setup.png")

    app.host_tournament("Friday Cup", "round_robin", 1, 60, "csw", True, 4, 0)
    time.sleep(0.6)
    app.client.host_command(action="add_bot", level=1)
    app.client.host_command(action="add_bot", level=1)
    time.sleep(0.8)
    app.client.host_command(action="remove_participant", client_id=app.client.client_id)
    time.sleep(0.6)
    save(app, "18_tournament_lobby.png")

    app.client.host_command(action="start")
    deadline = time.time() + 30
    while time.time() < deadline and (app.client.snapshot or {}).get("phase") != "playing":
        time.sleep(0.2)
    time.sleep(1.5)
    app._route_tournament()
    save(app, "19_tournament_game.png")

    deadline = time.time() + 180
    while time.time() < deadline and (app.client.snapshot or {}).get("phase") != "finished":
        time.sleep(0.4)
    app._route_tournament()
    time.sleep(0.3)
    save(app, "20_tournament_final.png")
    app.leave_game()
    time.sleep(0.2)


if __name__ == "__main__":
    main()
