"""Two-client network test: host, joiner, lobby, start and a move."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.net.client import NetClient
from tessera.net.server import GameServer
from tessera.session import Session

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
        time.sleep(0.05)
    return False


def main():
    session = Session(turn_seconds=120, allow_blank_recycle=True, seats=2)
    server = GameServer(session, port=0, host="127.0.0.1")
    port = server.start()

    host = NetClient()
    check("host connects", host.connect("127.0.0.1", port, "Host"))
    joiner = NetClient()
    check("joiner connects", joiner.connect("127.0.0.1", port, "Guest"))
    watcher = NetClient()
    check("watcher connects", watcher.connect("127.0.0.1", port, "Watcher", observe=True))
    check("watcher has no seat", watcher.seat is None and watcher.observer, (watcher.seat, watcher.observer))
    check("host sees the watcher", wait_for(lambda: len((host.snapshot or {}).get("observers", [])) == 1),
          (host.snapshot or {}).get("observers"))

    check("host sees lobby", wait_for(lambda: host.snapshot is not None))
    check("two seats taken", wait_for(lambda: sum(1 for s in host.snapshot["seats"] if s["taken"]) == 2),
          host.snapshot["seats"])
    check("host is host", host.is_host)
    check("joiner is not host", not joiner.is_host)

    check("different seats", wait_for(lambda: host.seat != joiner.seat), (host.seat, joiner.seat))

    host.host_command(action="start")
    check("game starts", wait_for(lambda: (host.snapshot or {}).get("phase") == "playing"))
    check("joiner also sees the game", wait_for(lambda: (joiner.snapshot or {}).get("phase") == "playing"))

    time.sleep(0.4)
    host_state = host.snapshot["state"]
    joiner_state = joiner.snapshot["state"]
    check("host sees own rack", "rack" in host_state["players"][host.seat],
          list(host_state["players"][host.seat].keys()))
    check("joiner's rack hidden from host", "rack" not in host_state["players"][joiner.seat])
    check("watcher sees no racks",
          wait_for(lambda: all("rack" not in p for p in (watcher.snapshot or {}).get("state", {}).get("players", []))))
    check("watcher snapshot has no viewer", (watcher.snapshot or {}).get("viewer") is None,
          (watcher.snapshot or {}).get("viewer"))
    check("viewer index matches seat", host.snapshot["viewer"] == host.seat and joiner.snapshot["viewer"] == joiner.seat,
          (host.snapshot["viewer"], joiner.snapshot["viewer"]))

    current = host_state["current"]
    actor = host if current == host.seat else joiner
    rack = actor.snapshot["state"]["players"][actor.seat]["rack"]
    check("14 tiles dealt to two players", host_state["bag"] == 86, host_state["bag"])

    # Play a simple two-letter word at the centre if the rack allows it.
    from tessera.lexicon import load_lexicon
    lexicon = load_lexicon()
    cells = None
    for first in rack:
        for second in rack:
            if first != second and lexicon.contains(first + second) and first != "?" and second != "?":
                cells = [(7, 7, first, False), (7, 8, second, False)]
                break
        if cells:
            break
    check("found an opening pair", cells is not None, rack)
    if cells:
        actor.play(cells)
        check("play broadcast to both",
              wait_for(lambda: host.snapshot["state"]["players"][actor.seat]["score"] > 0 and
                       joiner.snapshot["state"]["players"][actor.seat]["score"] > 0),
              (host.snapshot["state"]["players"][actor.seat]["score"],))
        check("turn moved on", host.snapshot["state"]["turn"] >= 2, host.snapshot["state"]["turn"])

    # A player who is not on turn must be rejected (checked on the next player now on turn).
    other = joiner if actor is host else host
    other.play([(0, 0, "A", False)])
    check("invalid play rejected", wait_for(lambda: bool(other.errors), 5), other.errors)
    other.errors.clear()

    before = host.snapshot["state"]["turn"]
    actor.play([(0, 0, "A", False)])
    check("out of turn play rejected", wait_for(lambda: bool(actor.errors), 5), actor.errors)
    check("turn unchanged after rejection", host.snapshot["state"]["turn"] == before)

    # Spectators cannot act.
    watcher.play([(0, 0, "A", False)])
    check("watcher cannot play", wait_for(lambda: bool(watcher.errors), 5), watcher.errors)

    host.close()
    joiner.close()
    watcher.close()
    server.stop()
    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
