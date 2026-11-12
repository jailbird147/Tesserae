"""Clock test: a player who runs out of time loses the turn."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.session import Session


def main():
    session = Session(turn_seconds=2, allow_blank_recycle=True, seats=2)
    first = session.join("One", "client-one")
    second = session.join("Two", "client-two")
    session.start()

    start_turn = session.snapshot("client-one")["state"]["turn"]
    time.sleep(3.5)
    snapshot = session.snapshot("client-one")
    turn = snapshot["state"]["turn"]
    notices = [n["text"] for n in snapshot["notices"]]
    ok = turn != start_turn and any("ran out of time" in text for text in notices)
    print("turn", start_turn, "->", turn)
    print("notices", notices[-3:])
    print("PASS" if ok else "FAIL")
    session.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
