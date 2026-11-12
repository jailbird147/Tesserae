"""Tournament tests: pairing, ladders, formats, and a real bot match."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tessera.tournament as tmod
from tessera.tournament import Tournament

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


class FakeSeat:
    def __init__(self):
        self.name = ""
        self.is_bot = False
        self.level = 3
        self.client_id = None
        self.connected = False


class FakeSession:
    counter = 0

    def __init__(self, **kwargs):
        self.phase = "playing"
        self.seat_list = [FakeSeat(), FakeSeat()]
        self.viewer = None

    def start(self):
        FakeSession.counter += 1
        self.phase = "finished"

    def snapshot(self, viewer):
        first = 400 if FakeSession.counter % 2 else 300
        second = 300 if first == 400 else 400
        return {
            "phase": self.phase,
            "state": {
                "players": [
                    {"name": self.seat_list[0].name, "score": first},
                    {"name": self.seat_list[1].name, "score": second},
                ]
            },
        }

    def close(self):
        self.phase = "closed"


def wait_finished(tournament, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        if tournament.phase == "finished":
            return True
        time.sleep(0.02)
    return False


def run_format(fmt, players=4, rounds=2):
    session_cls = tmod.Session
    tmod.Session = FakeSession
    old_between = tmod.BETWEEN_MATCH_SECONDS
    tmod.BETWEEN_MATCH_SECONDS = 0.02
    try:
        tournament = Tournament(name=f"Test {fmt}", fmt=fmt, rounds=rounds, turn_seconds=60, capacity=players)
        for _ in range(players):
            tournament.add_bot(1)
        tournament.start()
        tournament._auto_next_at = 0
        finished = wait_finished(tournament, 20)
        return tournament, finished
    finally:
        tmod.Session = session_cls
        tmod.BETWEEN_MATCH_SECONDS = old_between


class LiveSession(FakeSession):
    """A session that never finishes on its own, so a match can be interrupted."""

    def start(self):
        FakeSession.counter += 1


def run_walkover():
    session_cls = tmod.Session
    tmod.Session = LiveSession
    old_between = tmod.BETWEEN_MATCH_SECONDS
    tmod.BETWEEN_MATCH_SECONDS = 0.02
    try:
        tournament = Tournament(name="Walkover Cup", fmt="round_robin", turn_seconds=60, capacity=4)
        for _ in range(4):
            tournament.add_bot(1)
        tournament.start()
        tournament._auto_next_at = 0
        deadline = time.time() + 5
        while time.time() < deadline and tournament.phase != "playing":
            time.sleep(0.02)
        check("walkover test has a match", tournament.phase == "playing" and bool(tournament.current),
              tournament.phase)
        if tournament.current:
            quitter = tournament.by_id(tournament.current[0])
            other = tournament.by_id(tournament.current[1])
            tournament.leave(quitter.client_id)
            check("walkover ends the match", tournament.phase == "between", tournament.phase)
            check("walkover is recorded",
                  any(r["kind"] == "walkover" and r["winner"] == other.name
                      for r in tournament.results), tournament.results)
            check("quitting player is eliminated", quitter.eliminated)
            check("opponent is credited", other.wins >= 1, other.wins)
            check("walkover closes the session", tournament.session is None)
            tournament._auto_next_at = 0
            deadline = time.time() + 5
            while time.time() < deadline and tournament.phase != "playing":
                time.sleep(0.02)
            check("the ladder carries on", tournament.phase == "playing", tournament.phase)
        tournament.close()
        return tournament
    finally:
        tmod.Session = session_cls
        tmod.BETWEEN_MATCH_SECONDS = old_between


def run_tournament_away():
    session_cls = tmod.Session
    tmod.Session = LiveSession
    old_between = tmod.BETWEEN_MATCH_SECONDS
    tmod.BETWEEN_MATCH_SECONDS = 0.02
    try:
        tournament = Tournament(name="Away Cup", fmt="round_robin", turn_seconds=60, capacity=2)
        tournament.join("human-1", "Ada")
        tournament.add_bot(1)
        tournament.start()
        tournament._auto_next_at = 0
        deadline = time.time() + 5
        while time.time() < deadline and tournament.phase != "playing":
            time.sleep(0.02)
        check("away test has a match", tournament.phase == "playing", tournament.phase)

        tournament.mark_away("human-1")
        check("a drop holds the place", tournament.by_id("human-1").away_since > 0)
        tournament.rejoin("human-1")
        check("rejoining clears it", tournament.by_id("human-1").away_since == 0)
        check("the return is counted", tournament.by_id("human-1").reconnects == 1,
              tournament.by_id("human-1").reconnects)
        check("the match is still on", tournament.phase == "playing", tournament.phase)

        # Stay away past the grace: the opponent gets the match.
        tournament.reconnect_grace = 0.01
        tournament.mark_away("human-1")
        deadline = time.time() + 5
        while time.time() < deadline and not any(r["kind"] == "walkover"
                                                for r in tournament.results):
            time.sleep(0.02)
        check("a dropout forfeits the match",
              any(r["kind"] == "walkover" for r in tournament.results), tournament.results)
        check("and leaves the ladder", tournament.by_id("human-1").eliminated)
        tournament.close()
    finally:
        tmod.Session = session_cls
        tmod.BETWEEN_MATCH_SECONDS = old_between


def main():
    # Round robin: every pair once.
    tournament, finished = run_format("round_robin", players=4)
    check("round robin finishes", finished)
    matches = [r for r in tournament.results if r["kind"] == "match"]
    check("round robin plays 6 matches", len(matches) == 6, len(matches))
    check("round robin champion", bool(tournament.champion), tournament.champion)
    check("round robin standings", len(tournament.standings()) == 4)
    check("wins equal losses", sum(p.wins for p in tournament.participants) == sum(p.losses for p in tournament.participants))
    check("spread adds up", sum(p.spread for p in tournament.participants) == 0,
          [p.spread for p in tournament.participants])

    # Swiss: fixed number of rounds, everyone plays each round.
    tournament, finished = run_format("swiss", players=4, rounds=2)
    check("swiss finishes", finished)
    swiss_matches = [r for r in tournament.results if r["kind"] == "match"]
    check("swiss plays 2 rounds x 2 matches", len(swiss_matches) == 4, len(swiss_matches))
    check("swiss rounds recorded", max(r["round"] for r in swiss_matches) <= 2,
          [r["round"] for r in swiss_matches])
    for participant in tournament.participants:
        check(f"swiss {participant.name} played twice", participant.played == 2, participant.played)

    # Knockout: three matches for four players, one champion.
    tournament, finished = run_format("knockout", players=4)
    check("knockout finishes", finished)
    knock_matches = [r for r in tournament.results if r["kind"] == "match"]
    check("knockout plays 3 matches", len(knock_matches) == 3, len(knock_matches))
    check("knockout one survivor", sum(1 for p in tournament.participants if not p.eliminated) == 1,
          [p.eliminated for p in tournament.participants])
    check("knockout champion set", bool(tournament.champion), tournament.champion)

    # A player who walks out forfeits instead of stalling the ladder.
    run_walkover()
    # A dropped player is given a minute, then forfeits.
    run_tournament_away()

    # Real session path: two bots, one match.
    tournament = Tournament(name="Real", fmt="round_robin", rounds=1, turn_seconds=60, capacity=2)
    tournament.add_bot(1)
    tournament.add_bot(1)
    tournament.start()
    tournament._auto_next_at = 0
    finished = wait_finished(tournament, 180)
    check("real bot match finishes", finished, tournament.phase)
    if finished:
        check("real match has a result", len(tournament.results) == 1, tournament.results)
        check("real champion", bool(tournament.champion), tournament.champion)
        check("real scores recorded",
              tournament.participants[0].points_for + tournament.participants[1].points_for > 0,
              [p.points_for for p in tournament.participants])
    tournament.close()

    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
