"""Reconnection: a seat is held for a minute, three returns per game, then a forfeit."""

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


def wait_for(predicate, timeout=10.0):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def start_server(session):
    server = GameServer(session, port=0, host="127.0.0.1")
    port = server.start()
    return server, port


def test_game():
    session = Session(turn_seconds=120, seats=2)
    session.seat_list[1].name = "Bot Rookie"
    session.seat_list[1].is_bot = True
    session.seat_list[1].connected = True
    session.seat_list[1].level = 1
    server, port = start_server(session)

    client = NetClient()
    client.auto_reconnect = False          # the retries are driven by hand here
    check("client joins", client.connect("127.0.0.1", port, "Ada"))
    check("server hands out a token", bool(client.token), client.token[:8])
    identity = client.client_id
    token = client.token

    session.start()
    check("game starts", wait_for(lambda: (client.snapshot or {}).get("state") is not None))
    seat_before = client.seat

    client.close()
    check("a drop holds the seat",
          wait_for(lambda: session.seat_list[0].connected is False), session.seat_list[0].connected)
    check("the name is kept", session.seat_list[0].name == "Ada", session.seat_list[0].name)
    check("the seat is not handed to anyone else", session.seat_list[0].client_id == identity)

    back = NetClient()
    back.auto_reconnect = False
    check("the token takes the seat back", back.connect_rejoin("127.0.0.1", port, identity, token),
          back.connect_error)
    check("same seat", back.seat == seat_before, back.seat)
    check("the rack comes back",
          wait_for(lambda: bool((back.snapshot or {}).get("state"))), (back.snapshot or {}).get("state"))
    state = (back.snapshot or {}).get("state") or {}
    check("viewer still sees their own rack", state.get("players", [{}])[seat_before].get("rack") is not None)
    check("one reconnect counted", session.seat_list[0].reconnects == 1, session.seat_list[0].reconnects)
    check("seat marked connected again", session.seat_list[0].connected)

    # Two more returns are allowed; the fourth attempt is refused.
    for number in (2, 3):
        back.close()
        wait_for(lambda: session.seat_list[0].connected is False)
        again = NetClient()
        again.auto_reconnect = False
        ok = again.connect_rejoin("127.0.0.1", port, identity, token)
        check(f"return {number} allowed", ok, again.connect_error)
        back = again

    back.close()
    wait_for(lambda: session.seat_list[0].connected is False)
    refused = NetClient()
    refused.auto_reconnect = False
    check("the fourth return is refused",
          not refused.connect_rejoin("127.0.0.1", port, identity, token))
    check("with a reason", wait_for(lambda: bool(refused.reconnect_refused), 5), refused.reconnect_refused)
    refused.close()

    # Now leave for longer than the grace: the match is forfeited.
    session.reconnect_grace = 0.4
    check("forfeit after the grace period",
          wait_for(lambda: session.phase == "finished", 10), session.phase)
    check("forfeiting player is out", session.state.players[0].yielded)
    check("result says why", "forfeit" in (session.state.result_message or "").lower(),
          session.state.result_message)
    check("the other player wins", session.state.players[1].wins >= 1, session.state.players[1].wins)

    server.stop()


def test_lobby():
    session = Session(turn_seconds=120, seats=2)
    server, port = start_server(session)
    session.reconnect_grace = 0.3

    client = NetClient()
    client.auto_reconnect = False
    check("lobby client joins", client.connect("127.0.0.1", port, "Grace"))
    client.close()
    check("lobby seat held while away",
          wait_for(lambda: session.seat_list[0].connected is False), session.seat_list[0].connected)
    check("then freed", wait_for(lambda: session.seat_list[0].client_id is None, 5),
          session.seat_list[0].name)
    server.stop()


def test_auto_reconnect():
    session = Session(turn_seconds=120, seats=2)
    session.seat_list[1].name = "Bot Rookie"
    session.seat_list[1].is_bot = True
    session.seat_list[1].connected = True
    session.seat_list[1].level = 1
    server, port = start_server(session)

    client = NetClient()
    check("auto-reconnect client joins", client.connect("127.0.0.1", port, "Kit"))
    session.start()
    check("it has state", wait_for(lambda: bool((client.snapshot or {}).get("state"))))

    sock = client.socket
    sock.close()                      # an abrupt drop, not a deliberate close
    check("drop noticed", wait_for(lambda: client.connected is False, 5))
    check("client starts retrying", wait_for(lambda: client.reconnecting, 5),
          client.reconnect_note)
    check("it gets back in", wait_for(lambda: client.connected, 15), client.reconnect_note)
    check("with the same seat", client.seat == 0, client.seat)
    check("and no refusal", not client.reconnect_refused, client.reconnect_refused)
    client.close()
    server.stop()


def test_refused_join():
    session = Session(turn_seconds=120, seats=2)
    session.seat_list[1].name = "Bot Rookie"
    session.seat_list[1].is_bot = True
    session.seat_list[1].connected = True
    server, port = start_server(session)

    first = NetClient()
    first.auto_reconnect = False
    first.connect("127.0.0.1", port, "Early")
    session.start()

    latecomer = NetClient()
    latecomer.auto_reconnect = False
    check("a late join is refused", not latecomer.connect("127.0.0.1", port, "Late"))
    check("with the server's own reason", "already started" in latecomer.connect_error,
          latecomer.connect_error)
    latecomer.close()
    first.close()
    server.stop()


def test_bad_token():
    session = Session(turn_seconds=120, seats=2)
    server, port = start_server(session)

    client = NetClient()
    client.auto_reconnect = False
    client.connect("127.0.0.1", port, "Mallory")
    identity, token = client.client_id, client.token
    client.close()

    thief = NetClient()
    thief.auto_reconnect = False
    check("a wrong token is refused",
          not thief.connect_rejoin("127.0.0.1", port, identity, "not-the-token"))
    check("seat is still held for the owner", session.seat_list[0].client_id == identity)
    thief.close()

    owner = NetClient()
    owner.auto_reconnect = False
    check("the owner can still get in", owner.connect_rejoin("127.0.0.1", port, identity, token),
          owner.connect_error)
    owner.close()
    server.stop()


def main():
    test_game()
    test_lobby()
    test_auto_reconnect()
    test_refused_join()
    test_bad_token()
    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
