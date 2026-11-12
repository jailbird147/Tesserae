"""Tournament server and UI routing test."""

import os
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["TESSERA_HEADLESS"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from tessera.net.client import NetClient
from tessera.net.server import GameServer
from tessera.tournament import Tournament
from tessera.ui.app import App
from tessera.ui.game_screen import GameScreen
from tessera.ui.tournament_screen import TournamentScreen

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


def wait_for(predicate, timeout=20.0):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def test_server():
    tournament = Tournament(name="Server Cup", fmt="round_robin", turn_seconds=60, capacity=2)
    tournament.add_bot(1)
    tournament.add_bot(1)
    server = GameServer(None, port=0, host="127.0.0.1", tournament=tournament)
    port = server.start()

    watcher = NetClient()
    check("client joins the tournament", watcher.connect("127.0.0.1", port, "Watcher", observe=True))
    check("tournament snapshot arrives",
          wait_for(lambda: (watcher.snapshot or {}).get("mode") == "tournament"))
    snapshot = watcher.snapshot
    check("lobby phase", snapshot.get("phase") == "lobby", snapshot.get("phase"))
    check("two bots in the roster", len(snapshot["tournament"]["standings"]) == 2)

    tournament.start()
    check("match starts", wait_for(lambda: (watcher.snapshot or {}).get("phase") == "playing", 15),
          (watcher.snapshot or {}).get("phase"))
    playing = watcher.snapshot or {}
    check("match state is merged", bool(playing.get("state")), list(playing.keys())[:6])
    check("watcher sees no racks",
          all("rack" not in p for p in playing.get("state", {}).get("players", [])))
    check("tournament info in the match snapshot", bool(playing.get("tournament")))

    finished = wait_for(lambda: (watcher.snapshot or {}).get("phase") == "finished", 180)
    check("tournament finishes", finished, (watcher.snapshot or {}).get("phase"))
    if finished:
        final = (watcher.snapshot or {})["tournament"]
        check("champion recorded", bool(final.get("champion")), final.get("champion"))
        check("standings have results",
              any(p["played"] >= 1 for p in final["standings"]), final["standings"])

    watcher.close()
    server.stop()


class FakeClient:
    def __init__(self):
        self.snapshot = None
        self.is_host = True
        self.client_id = "me"
        self.observer = False
        self.connected = True
        self.commands = []

    def host_command(self, **payload):
        self.commands.append(payload)


def test_router():
    app = App()
    fake = FakeClient()
    app.client = fake
    fake.snapshot = {"mode": "tournament", "phase": "lobby", "tournament": {"phase": "lobby"}}
    app._route_tournament()
    check("lobby shows the tournament board", isinstance(app.screen, TournamentScreen), type(app.screen).__name__)

    fake.snapshot = {"mode": "tournament", "phase": "playing", "tournament": {"phase": "playing"},
                     "state": {"game_over": False}}
    app._route_tournament()
    check("playing shows the board", isinstance(app.screen, GameScreen), type(app.screen).__name__)
    check("game screen knows it is a tournament", getattr(app.screen, "tournament_mode", False))

    fake.snapshot = {"mode": "tournament", "phase": "between", "tournament": {"phase": "between"},
                     "state": None}
    app._route_tournament()
    check("between matches shows the tournament board", isinstance(app.screen, TournamentScreen))

    # Lobby: clicking "remove" next to a bot tells the server to drop it.
    fake.snapshot = {
        "mode": "tournament", "phase": "lobby", "state": None,
        "tournament": {
            "phase": "lobby", "capacity": 4,
            "standings": [
                {"name": "Me", "client_id": "me", "is_bot": False, "rank": 1},
                {"name": "Bot Rookie", "client_id": "bot:1", "is_bot": True, "rank": 2},
            ],
        },
    }
    app._route_tournament()
    screen = app.screen
    rows = screen._lobby_rows()
    bot_row = rows[1][0]
    screen.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=(bot_row.right - 20, bot_row.centery)))
    check("removing a bot sends a host command",
          bool(fake.commands) and fake.commands[-1].get("action") == "remove_participant"
          and fake.commands[-1].get("client_id") == "bot:1", fake.commands[-1:])

    app.client = None
    app.leave_game()


def main():
    test_server()
    test_router()
    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
