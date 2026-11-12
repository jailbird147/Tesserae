"""Tournaments: a series of matches run by the host's server.

Formats
-------
swiss        fixed number of rounds, players paired on wins then spread
round_robin  every player meets every other player once
knockout     single elimination; lose and you are out

One match is played at a time. The two players play, everyone else watches,
then the result goes on the ladder and the next match starts.
"""

from __future__ import annotations

import itertools
import random
import threading
import time
import uuid
from dataclasses import dataclass, field

from .lexicon import lexicon_label
from .rules import RulesError
from .session import MAX_RECONNECTS, RECONNECT_GRACE, Session

FORMATS = {
    "swiss": {
        "label": "Swiss",
        "blurb": "Fixed rounds, paired on wins then spread.",
    },
    "round_robin": {
        "label": "Round robin",
        "blurb": "Everyone plays everyone once.",
    },
    "knockout": {
        "label": "Knockout",
        "blurb": "Single elimination. Lose and you are out.",
    },
}

BETWEEN_MATCH_SECONDS = 6.0


@dataclass
class Participant:
    client_id: str
    name: str
    is_bot: bool = False
    level: int = 3
    wins: int = 0
    losses: int = 0
    draws: int = 0
    points_for: int = 0
    points_against: int = 0
    byes: int = 0
    eliminated: bool = False
    reconnects: int = 0
    away_since: float = 0.0
    met: set[str] = field(default_factory=set)

    @property
    def played(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def spread(self) -> int:
        return self.points_for - self.points_against

    def public(self, rank: int) -> dict:
        return {
            "rank": rank,
            "name": self.name,
            "client_id": self.client_id,
            "is_bot": self.is_bot,
            "away": bool(self.away_since),
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "byes": self.byes,
            "spread": self.spread,
            "points_for": self.points_for,
            "points_against": self.points_against,
            "eliminated": self.eliminated,
            "played": self.played,
        }


class Tournament:
    def __init__(
        self,
        name: str = "Tessera Cup",
        fmt: str = "swiss",
        rounds: int = 3,
        turn_seconds: int = 120,
        lexicon: str = "csw",
        allow_blank_recycle: bool = True,
        allow_hints: bool = True,
        bingo_bonus: bool = True,
        end_after_six_scoreless: bool = True,
        minimum_word_length: int = 0,
        capacity: int = 8,
    ) -> None:
        self.name = name or "Tessera Cup"
        self.format = fmt if fmt in FORMATS else "swiss"
        self.rounds = max(1, min(9, int(rounds)))
        self.turn_seconds = int(turn_seconds)
        self.lexicon_name = lexicon
        self.allow_blank_recycle = bool(allow_blank_recycle)
        self.allow_hints = bool(allow_hints)
        self.bingo_bonus = bool(bingo_bonus)
        self.end_after_six_scoreless = bool(end_after_six_scoreless)
        self.minimum_word_length = int(minimum_word_length)
        self.capacity = max(2, min(16, int(capacity)))

        self.participants: list[Participant] = []
        self.phase = "lobby"          # lobby | playing | between | finished
        self.round_number = 0
        self.session: Session | None = None
        self.current: tuple[str, str] | None = None
        self.results: list[dict] = []
        self.champion: str | None = None
        self.lock = threading.RLock()
        self.reconnect_grace = RECONNECT_GRACE

        self._queue: list[tuple[str, str, int]] = []
        self._waiting: list[str] = []
        self._auto_next_at = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._rng = random.Random()

    # ------------------------------------------------------------------ roster
    def by_id(self, client_id: str) -> Participant | None:
        for participant in self.participants:
            if participant.client_id == client_id:
                return participant
        return None

    def join(self, client_id: str, name: str) -> None:
        with self.lock:
            if self.phase != "lobby":
                raise RulesError("That tournament has already started.")
            if self.by_id(client_id):
                return
            if len(self.participants) >= self.capacity:
                raise RulesError("The tournament is full.")
            clean = (name or "Player").strip()[:20]
            if any(p.name == clean for p in self.participants):
                clean = f"{clean} 2"
            self.participants.append(Participant(client_id=client_id, name=clean))

    def leave(self, client_id: str) -> None:
        with self.lock:
            participant = self.by_id(client_id)
            if participant is None:
                return
            if self.phase == "lobby":
                self.participants.remove(participant)
            elif not participant.eliminated:
                self._withdraw(participant)

    def mark_away(self, client_id: str) -> None:
        """A connection went away: hold their place for the grace period."""
        with self.lock:
            participant = self.by_id(client_id)
            if participant is None or participant.is_bot:
                return
            participant.away_since = time.monotonic()

    def rejoin(self, client_id: str) -> str:
        """Take a held place back after a drop."""
        with self.lock:
            participant = self.by_id(client_id)
            if participant is None:
                raise RulesError("You are no longer in this tournament.")
            if participant.reconnects >= MAX_RECONNECTS:
                raise RulesError("You have used all three reconnections in this match.")
            participant.reconnects += 1
            participant.away_since = 0.0
            rejoin = getattr(self.session, "rejoin", None)
            if rejoin is not None:
                try:
                    rejoin(client_id, consume=False)
                except RulesError:
                    pass
            return participant.name

    def _expire_away(self) -> None:
        now = time.monotonic()
        for participant in list(self.participants):
            if participant.is_bot or participant.eliminated or not participant.away_since:
                continue
            if now - participant.away_since < self.reconnect_grace:
                continue
            participant.away_since = 0.0
            if self.phase == "lobby":
                self.participants.remove(participant)
            else:
                self._withdraw(participant)

    def _withdraw(self, participant: Participant) -> None:
        """A player who leaves forfeits rather than stalling the ladder."""
        participant.eliminated = True

        # Every match they were still down to play goes to the opponent.
        keep: list[tuple[str, str, int]] = []
        for a_id, b_id, round_number in self._queue:
            if participant.client_id not in (a_id, b_id):
                keep.append((a_id, b_id, round_number))
                continue
            other = self.by_id(b_id if a_id == participant.client_id else a_id)
            if other is None or other.eliminated:
                continue
            other.wins += 1
            self.results.append({
                "round": round_number, "kind": "walkover", "winner": other.name,
                "a": other.name, "b": participant.name, "a_score": 0, "b_score": 0,
            })
            if self.format == "knockout":
                self._waiting.append(other.client_id)
        self._queue = keep

        if self.phase == "playing" and self.current and participant.client_id in self.current:
            self._award_walkover(participant)

    def _award_walkover(self, quitter: Participant) -> None:
        """End the match in progress when one of the two players has gone."""
        pair = self.current
        session, self.session = self.session, None
        self.current = None
        scores: dict[str, int] = {}
        order = list(pair) if pair else []
        if session is not None:
            try:
                state = (session.snapshot(None) or {}).get("state") or {}
                scores = {player["name"]: player["score"] for player in state.get("players", [])}
            except Exception:
                scores = {}
            session.close()

        first = self.by_id(order[0]) if order else None
        second = self.by_id(order[1]) if len(order) > 1 else None
        winner = second if first is quitter else first
        if winner is None:
            self.phase = "between"
            self._auto_next_at = time.monotonic() + 1.0
            return
        winner.wins += 1
        quitter.losses += 1
        first_score = scores.get(first.name, 0) if first else 0
        second_score = scores.get(second.name, 0) if second else 0
        if first is not None and second is not None:
            first.points_for += first_score
            first.points_against += second_score
            second.points_for += second_score
            second.points_against += first_score
        self.results.append({
            "round": self.round_number, "kind": "walkover", "winner": winner.name,
            "a": first.name if first else "?", "b": second.name if second else "?",
            "a_score": first_score, "b_score": second_score,
        })
        if self.format == "knockout":
            self._waiting.append(winner.client_id)
        self.phase = "between"
        self._auto_next_at = time.monotonic() + 2.0

    def add_bot(self, level: int = 3) -> None:
        with self.lock:
            if self.phase != "lobby" or len(self.participants) >= self.capacity:
                return
            level = max(1, min(5, int(level)))
            from .bot import level_info
            base = f"Bot {level_info(level)['name']}"
            name = base
            index = 2
            while any(p.name == name for p in self.participants):
                name = f"{base} {index}"
                index += 1
            self.participants.append(
                Participant(client_id=f"bot:{uuid.uuid4().hex}", name=name, is_bot=True, level=level)
            )

    def set_bot_level(self, client_id: str, level: int) -> None:
        with self.lock:
            if self.phase != "lobby":
                return
            participant = self.by_id(client_id)
            if participant is None or not participant.is_bot:
                return
            level = max(1, min(5, int(level)))
            from .bot import level_info
            participant.level = level
            base = f"Bot {level_info(level)['name']}"
            name = base
            index = 2
            while any(p.name == name and p is not participant for p in self.participants):
                name = f"{base} {index}"
                index += 1
            participant.name = name

    def remove_participant(self, client_id: str) -> None:
        with self.lock:
            if self.phase != "lobby":
                return
            participant = self.by_id(client_id)
            if participant is not None:
                self.participants.remove(participant)

    # ------------------------------------------------------------------ ladder
    def standings(self) -> list[Participant]:
        return sorted(
            self.participants,
            key=lambda p: (p.wins, p.spread, p.points_for),
            reverse=True,
        )

    # ------------------------------------------------------------------- start
    def start(self) -> None:
        with self.lock:
            if self.phase != "lobby":
                return
            if len(self.participants) < 2:
                raise RulesError("A tournament needs at least two players.")
            self.round_number = 0
            self.results.clear()
            self.champion = None
            self._queue.clear()
            self._waiting.clear()
            for participant in self.participants:
                participant.wins = participant.losses = participant.draws = 0
                participant.points_for = participant.points_against = 0
                participant.byes = 0
                participant.eliminated = False
                participant.met.clear()

            if self.format == "round_robin":
                pairs = list(itertools.combinations([p.client_id for p in self.participants], 2))
                self._rng.shuffle(pairs)
                self._queue = [(a, b, index + 1) for index, (a, b) in enumerate(pairs)]
            elif self.format == "knockout":
                ids = [p.client_id for p in self.participants]
                self._rng.shuffle(ids)
                if len(ids) % 2 == 1:
                    bye = self.by_id(ids.pop())
                    if bye is not None:
                        bye.byes += 1
                        bye.wins += 1
                        self._waiting.append(bye.client_id)
                        self.results.append({
                            "round": 1, "kind": "bye", "winner": bye.name,
                            "a": bye.name, "b": "bye", "a_score": 0, "b_score": 0,
                        })
                self._queue = [
                    (ids[i], ids[i + 1], 1) for i in range(0, len(ids) - 1, 2)
                ]
                self.round_number = 1
            else:
                self._build_swiss_round()

            self.phase = "between"
            self._auto_next_at = time.monotonic() + 1.0

    def _build_swiss_round(self) -> None:
        if self.round_number >= self.rounds:
            return
        active = [p for p in self.participants if not p.eliminated]
        if len(active) < 2:
            return
        self.round_number += 1
        pool = sorted(active, key=lambda p: (p.wins, p.spread), reverse=True)
        matches: list[tuple[Participant, Participant]] = []
        while len(pool) >= 2:
            first = pool.pop(0)
            partner = next((c for c in pool if c.client_id not in first.met), None)
            if partner is None:
                partner = pool[0]
            pool.remove(partner)
            matches.append((first, partner))
        if pool:
            loner = pool.pop()
            loner.byes += 1
            loner.wins += 1
            self.results.append({
                "round": self.round_number, "kind": "bye", "winner": loner.name,
                "a": loner.name, "b": "bye", "a_score": 0, "b_score": 0,
            })
        for first, second in matches:
            self._queue.append((first.client_id, second.client_id, self.round_number))

    # -------------------------------------------------------------- match flow
    def _loop(self) -> None:
        while not self._stop.wait(0.2):
            with self.lock:
                if self.phase != "finished":
                    self._expire_away()
                if self.phase == "playing" and self.session is not None:
                    if getattr(self.session, "phase", "") == "finished":
                        self._finish_match()
                elif self.phase == "between" and time.monotonic() >= self._auto_next_at:
                    self._advance()

    def _advance(self) -> None:
        if self._queue:
            self._start_next()
            return
        if self.format == "swiss":
            self._build_swiss_round()
            if self._queue:
                self._start_next()
                return
        if self.format == "knockout":
            self._advance_knockout_round()
            if self._queue:
                self._start_next()
                return
        self._finish_tournament()

    def _start_next(self) -> None:
        a_id, b_id, round_number = self._queue.pop(0)
        first = self.by_id(a_id)
        second = self.by_id(b_id)
        if first is None or second is None or first.eliminated or second.eliminated:
            self._advance()
            return

        session = Session(
            turn_seconds=self.turn_seconds,
            allow_blank_recycle=self.allow_blank_recycle,
            seats=2,
            lexicon=self.lexicon_name,
            allow_hints=self.allow_hints,
            bingo_bonus=self.bingo_bonus,
            end_after_six_scoreless=self.end_after_six_scoreless,
            minimum_word_length=self.minimum_word_length,
        )
        first.reconnects = 0
        second.reconnects = 0
        for index, participant in enumerate((first, second)):
            seat = session.seat_list[index]
            seat.name = participant.name
            seat.is_bot = participant.is_bot
            seat.level = participant.level
            seat.client_id = None if participant.is_bot else participant.client_id
            seat.connected = True
        try:
            session.start()
        except RulesError:
            session.close()
            self._advance()
            return

        self.session = session
        self.current = (first.client_id, second.client_id)
        self.round_number = max(self.round_number, round_number)
        self.phase = "playing"

    def _finish_match(self) -> None:
        session = self.session
        if session is None or self.current is None:
            return
        snapshot = session.snapshot(None)
        state = snapshot.get("state") or {}
        scores = {player["name"]: player["score"] for player in state.get("players", [])}
        first = self.by_id(self.current[0])
        second = self.by_id(self.current[1])
        self.session = None
        self.current = None
        session.close()

        if first is None or second is None:
            self.phase = "between"
            self._auto_next_at = time.monotonic() + 1.0
            return

        first_score = scores.get(first.name, 0)
        second_score = scores.get(second.name, 0)
        first.met.add(second.client_id)
        second.met.add(first.client_id)
        first.points_for += first_score
        first.points_against += second_score
        second.points_for += second_score
        second.points_against += first_score

        winner: Participant | None = None
        if first_score > second_score:
            winner = first
            first.wins += 1
            second.losses += 1
        elif second_score > first_score:
            winner = second
            second.wins += 1
            first.losses += 1
        else:
            first.draws += 1
            second.draws += 1

        if self.format == "knockout" and winner is None:
            self.results.append({
                "round": self.round_number, "kind": "draw", "winner": "replay",
                "a": first.name, "b": second.name,
                "a_score": first_score, "b_score": second_score,
            })
            self._queue.insert(0, (first.client_id, second.client_id, self.round_number))
            self.phase = "between"
            self._auto_next_at = time.monotonic() + 2.0
            return

        self.results.append({
            "round": self.round_number, "kind": "match",
            "winner": winner.name if winner else "draw",
            "a": first.name, "b": second.name,
            "a_score": first_score, "b_score": second_score,
        })
        if self.format == "knockout" and winner is not None:
            loser = second if winner is first else first
            loser.eliminated = True
            self._waiting.append(winner.client_id)

        self.phase = "between"
        self._auto_next_at = time.monotonic() + BETWEEN_MATCH_SECONDS

    def _advance_knockout_round(self) -> None:
        waiting = [cid for cid in self._waiting
                   if (player := self.by_id(cid)) is not None and not player.eliminated]
        self._waiting = []
        if len(waiting) <= 1:
            return
        self.round_number += 1
        if len(waiting) % 2 == 1:
            bye_id = waiting.pop()
            bye = self.by_id(bye_id)
            if bye is not None:
                bye.byes += 1
                bye.wins += 1
                self._waiting.append(bye.client_id)
                self.results.append({
                    "round": self.round_number, "kind": "bye", "winner": bye.name,
                    "a": bye.name, "b": "bye", "a_score": 0, "b_score": 0,
                })
        for index in range(0, len(waiting) - 1, 2):
            self._queue.append((waiting[index], waiting[index + 1], self.round_number))

    def _finish_tournament(self) -> None:
        if self.phase == "finished":
            return
        if self.session is not None:
            self.session.close()
            self.session = None
        self.current = None
        ranked = self.standings()
        self.champion = ranked[0].name if ranked else None
        self.phase = "finished"

    # ------------------------------------------------------------------ output
    def snapshot(self, client_id: str | None) -> dict:
        with self.lock:
            session_snapshot = self.session.snapshot(client_id) if self.session is not None else None
            payload = {
                "name": self.name,
                "format": self.format,
                "format_label": FORMATS[self.format]["label"],
                "format_blurb": FORMATS[self.format]["blurb"],
                "phase": self.phase,
                "round": self.round_number,
                "rounds": self.rounds,
                "capacity": self.capacity,
                "champion": self.champion,
                "standings": [p.public(index + 1) for index, p in enumerate(self.standings())],
                "results": list(self.results[-12:]),
                "current": self._pair_payload(self.current),
                "queue": len(self._queue),
                "settings": {
                    "turn_seconds": self.turn_seconds,
                    "lexicon": self.lexicon_name,
                    "lexicon_label": lexicon_label(self.lexicon_name),
                    "allow_blank_recycle": self.allow_blank_recycle,
                    "allow_hints": self.allow_hints,
                    "bingo_bonus": self.bingo_bonus,
                    "end_after_six_scoreless": self.end_after_six_scoreless,
                    "minimum_word_length": self.minimum_word_length,
                    "max_seats": 2,
                },
                "next_start": max(0.0, round(self._auto_next_at - time.monotonic(), 1)) if self.phase == "between" else 0.0,
            }

            if session_snapshot is not None:
                merged = dict(session_snapshot)
                merged["mode"] = "tournament"
                merged["tournament"] = payload
                # The outer phase stays the tournament's own phase. A match that
                # has just ended keeps reporting "playing" for the moment it
                # takes the loop to record the result, so nobody ever sees an
                # empty ladder, or "finished" with no champion.
                merged["match_phase"] = session_snapshot.get("phase")
                merged["phase"] = self.phase
                return merged

            return {
                "mode": "tournament",
                "phase": self.phase,
                "tournament": payload,
                "viewer": None,
                "state": None,
                "settings": payload["settings"],
                "server_now": time.time(),
                "observers": [],
                "notices": [],
            }

    def _pair_payload(self, pair) -> dict | None:
        if not pair:
            return None
        first = self.by_id(pair[0])
        second = self.by_id(pair[1])
        return {
            "a": first.name if first else "?",
            "b": second.name if second else "?",
            "round": self.round_number,
        }

    def close(self) -> None:
        self._stop.set()
        with self.lock:
            if self.session is not None:
                self.session.close()
                self.session = None
