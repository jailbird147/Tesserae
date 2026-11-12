"""Authoritative game session: lobby, clocks, bots and turn handling."""

from __future__ import annotations

import random
import threading
import time
import uuid
from dataclasses import dataclass

from .analysis import classify, estimate_rating, main_word_pattern
from .bot import choose_bot_action, level_info
from .engine import shared_engine
from .lexicon import (
    Lexicon,
    lexicon_dawg,
    lexicon_label,
    load_lexicon,
    resolve as resolve_lexicon,
    strategy_lexicon,
)
from .rules import GameState, RulesError


RECONNECT_GRACE = 60.0     # seconds a dropped player has to come back
MAX_RECONNECTS = 3         # per game, per player


@dataclass
class Seat:
    name: str
    is_bot: bool = False
    level: int = 3
    client_id: str | None = None
    connected: bool = False
    reconnects: int = 0
    away_since: float = 0.0

    def public(self) -> dict:
        return {
            "name": self.name,
            "is_bot": self.is_bot,
            "level": self.level,
            "connected": self.connected,
            "taken": self.is_bot or self.client_id is not None,
        }


class Session:
    def __init__(
        self,
        turn_seconds: int = 120,
        allow_blank_recycle: bool = True,
        seats: int = 2,
        max_seats: int = 4,
        lexicon: str = "csw",
        allow_hints: bool = True,
        bingo_bonus: bool = True,
        end_after_six_scoreless: bool = True,
        minimum_word_length: int = 0,
    ) -> None:
        self.turn_seconds = int(turn_seconds)
        self.allow_blank_recycle = bool(allow_blank_recycle)
        self.allow_hints = bool(allow_hints)
        self.bingo_bonus = bool(bingo_bonus)
        self.end_after_six_scoreless = bool(end_after_six_scoreless)
        self.minimum_word_length = int(minimum_word_length)
        self.lexicon_name = resolve_lexicon(lexicon)
        self.dawg = lexicon_dawg(self.lexicon_name)
        self.max_seats = max(2, min(4, max_seats))
        self.seat_list: list[Seat] = [Seat(name=f"Seat {i + 1}") for i in range(self.max_seats)]
        self.phase = "lobby"
        self.observers: dict[str, str] = {}
        self.state: GameState | None = None
        self.lock = threading.RLock()
        self.lexicon: Lexicon = load_lexicon(self.lexicon_name)
        self.server_now = time.time
        self.address = ""

        self._deadline = 0.0
        self._turn_marker: tuple[int, int] | None = None
        self._bot_marker: tuple[int, int] | None = None
        self._bot_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._notices: list[dict] = []
        self._notice_id = 1
        self._rng = random.Random()
        self.last_error = ""
        self._closed = False
        self._analysis_running = False
        self.reconnect_grace = RECONNECT_GRACE

    # ------------------------------------------------------------------ lobby
    def set_settings(self, turn_seconds: int | None = None, allow_blank_recycle: bool | None = None,
                     seats: int | None = None, lexicon: str | None = None,
                     allow_hints: bool | None = None, bingo_bonus: bool | None = None,
                     end_after_six_scoreless: bool | None = None,
                     minimum_word_length: int | None = None) -> None:
        with self.lock:
            if self.phase != "lobby":
                return
            if lexicon is not None and resolve_lexicon(lexicon) != self.lexicon_name:
                self.lexicon_name = resolve_lexicon(lexicon)
                self.dawg = lexicon_dawg(self.lexicon_name)
                self.lexicon = load_lexicon(self.lexicon_name)
            if turn_seconds is not None:
                self.turn_seconds = max(60, min(180, int(turn_seconds)))
            if allow_blank_recycle is not None:
                self.allow_blank_recycle = bool(allow_blank_recycle)
            if allow_hints is not None:
                self.allow_hints = bool(allow_hints)
            if bingo_bonus is not None:
                self.bingo_bonus = bool(bingo_bonus)
            if end_after_six_scoreless is not None:
                self.end_after_six_scoreless = bool(end_after_six_scoreless)
            if minimum_word_length is not None:
                self.minimum_word_length = max(0, min(6, int(minimum_word_length)))
            if seats is not None:
                self._resize(max(2, min(4, int(seats))))

    def _resize(self, count: int) -> None:
        if count == len(self.seat_list):
            return
        if count < len(self.seat_list):
            # Keep occupied seats, drop free ones from the end.
            while len(self.seat_list) > count:
                if self.seat_list[-1].client_id is not None:
                    break
                self.seat_list.pop()
        while len(self.seat_list) < count:
            self.seat_list.append(Seat(name=f"Seat {len(self.seat_list) + 1}"))
        self.max_seats = len(self.seat_list)

    def join(self, name: str, client_id: str | None = None) -> int:
        with self.lock:
            if self.phase != "lobby":
                raise RulesError("That game has already started. Ask the host for a new lobby.")
            client_id = client_id or uuid.uuid4().hex
            for index, seat in enumerate(self.seat_list):
                if seat.client_id == client_id:
                    seat.connected = True
                    return index
            for index, seat in enumerate(self.seat_list):
                if not seat.is_bot and seat.client_id is None:
                    seat.name = name[:20] or f"Player {index + 1}"
                    seat.client_id = client_id
                    seat.connected = True
                    return index
            raise RulesError("The game is full.")

    def join_observer(self, client_id: str, name: str) -> None:
        with self.lock:
            self.observers[client_id] = (name or "Watcher")[:20]

    def leave(self, client_id: str) -> None:
        """A connection went away: hold the seat for the grace period."""
        with self.lock:
            self.observers.pop(client_id, None)
            for index, seat in enumerate(self.seat_list):
                if seat.client_id == client_id:
                    seat.connected = False
                    seat.away_since = time.monotonic()
                    if self.state is not None:
                        self.state.set_connected(index, False)
                    return

    def rejoin(self, client_id: str, consume: bool = True) -> int | None:
        """Take a held seat back. Returns the seat index, or None for observers."""
        with self.lock:
            if client_id in self.observers:
                return None
            for index, seat in enumerate(self.seat_list):
                if seat.client_id != client_id:
                    continue
                if consume:
                    if seat.reconnects >= MAX_RECONNECTS:
                        raise RulesError("You have used all three reconnections in this game.")
                    seat.reconnects += 1
                seat.connected = True
                seat.away_since = 0.0
                if self.state is not None:
                    self.state.set_connected(index, True)
                return index
            raise RulesError("Your seat is no longer being held. Ask for a new game.")

    def _expire_away(self) -> None:
        """Seats held past the grace period are forfeited (or freed in a lobby)."""
        now = time.monotonic()
        for index, seat in enumerate(self.seat_list):
            if seat.is_bot or seat.connected or seat.client_id is None or not seat.away_since:
                continue
            if now - seat.away_since < self.reconnect_grace:
                continue
            seat.away_since = 0.0
            name = seat.name
            if self.phase == "lobby":
                seat.client_id = None
                seat.connected = False
                seat.name = f"Seat {index + 1}"
                self._notice(f"{name} left the lobby.", kind="system")
                continue
            if self.state is None:
                continue
            self.state.forfeit(index)
            self._notice(
                f"{name} did not come back within a minute and forfeits.",
                kind="system",
            )
            if self.state.game_over:
                self._finish()

    def add_bot(self, index: int, level: int = 3) -> None:
        with self.lock:
            if self.phase != "lobby" or not (0 <= index < len(self.seat_list)):
                return
            seat = self.seat_list[index]
            if seat.client_id is not None:
                return
            seat.is_bot = True
            seat.level = max(1, min(5, int(level)))
            seat.name = f"Bot {level_info(seat.level)['name']}"
            seat.connected = True

    def set_bot_level(self, index: int, level: int) -> None:
        with self.lock:
            if self.phase != "lobby" or not (0 <= index < len(self.seat_list)):
                return
            seat = self.seat_list[index]
            if not seat.is_bot:
                return
            seat.level = max(1, min(5, int(level)))
            seat.name = f"Bot {level_info(seat.level)['name']}"

    def remove_bot(self, index: int) -> None:
        with self.lock:
            if self.phase != "lobby" or not (0 <= index < len(self.seat_list)):
                return
            seat = self.seat_list[index]
            if seat.is_bot:
                seat.is_bot = False
                seat.connected = False
                seat.name = f"Seat {index + 1}"

    # ------------------------------------------------------------------- game
    def start(self) -> None:
        with self.lock:
            if self.phase != "lobby":
                return
            seats = [seat for seat in self.seat_list if seat.is_bot or seat.client_id is not None]
            if len(seats) < 2:
                raise RulesError("Fill at least two seats first.")
            seats = seats[:4]
            self.seat_list = seats
            self.max_seats = len(seats)
            self.state = GameState(
                [seat.name for seat in seats],
                bots=[seat.is_bot for seat in seats],
                levels=[seat.level for seat in seats],
                turn_seconds=self.turn_seconds,
                allow_blank_recycle=self.allow_blank_recycle,
                lexicon=self.lexicon,
                rng=self._rng,
                bingo_bonus=self.bingo_bonus,
                end_after_six_scoreless=self.end_after_six_scoreless,
                minimum_word_length=self.minimum_word_length,
            )
            self.phase = "playing"
            for seat in self.seat_list:
                seat.reconnects = 0
                seat.away_since = 0.0
            self._reset_clock()
            self._notice("The game begins. Good luck!", kind="system")

    def rematch(self) -> None:
        with self.lock:
            if self.phase not in ("finished", "playing"):
                return
            names = [seat.name for seat in self.seat_list]
            levels = [seat.level for seat in self.seat_list]
            bots = [seat.is_bot for seat in self.seat_list]
            self.state = GameState(
                names,
                bots=bots,
                levels=levels,
                turn_seconds=self.turn_seconds,
                allow_blank_recycle=self.allow_blank_recycle,
                lexicon=self.lexicon,
                rng=self._rng,
                bingo_bonus=self.bingo_bonus,
                end_after_six_scoreless=self.end_after_six_scoreless,
                minimum_word_length=self.minimum_word_length,
            )
            self.phase = "playing"
            for seat in self.seat_list:
                seat.reconnects = 0
                seat.away_since = 0.0
            self._reset_clock()
            self._notice("Rematch! New racks, same grudges.", kind="system")

    def _seat_of(self, client_id: str) -> int:
        for index, seat in enumerate(self.seat_list):
            if seat.client_id == client_id:
                return index
        raise RulesError("You are not seated in this game.")

    def _require_state(self) -> GameState:
        if self.phase != "playing" or self.state is None:
            raise RulesError("The game is not running.")
        return self.state

    def play(self, client_id: str, cells: list[tuple[int, int, str, bool]]) -> None:
        with self.lock:
            state = self._require_state()
            seat = self._seat_of(client_id)
            try:
                result = state.play(seat, cells)
            except RulesError as exc:
                self._notice(str(exc), kind="error", seat=seat)
                raise
            words = ", ".join(f"{word} ({score})" for word, score in result.words)
            self._notice(
                f"{self.seat_list[seat].name} played {words} for {result.score}.",
                kind="play",
                seat=seat,
            )
            if state.game_over:
                self._finish()

    def exchange(self, client_id: str, letters: list[str]) -> None:
        with self.lock:
            state = self._require_state()
            seat = self._seat_of(client_id)
            state.exchange(seat, letters)
            self._notice(
                f"{self.seat_list[seat].name} exchanged {len(letters)} tiles.",
                kind="exchange",
                seat=seat,
            )

    def pass_turn(self, client_id: str) -> None:
        with self.lock:
            state = self._require_state()
            seat = self._seat_of(client_id)
            state.pass_turn(seat)
            self._notice(f"{self.seat_list[seat].name} passed.", kind="pass", seat=seat)

    def recycle_blanks(self, client_id: str) -> None:
        with self.lock:
            state = self._require_state()
            seat = self._seat_of(client_id)
            state.recycle_blanks(seat)
            self._notice(
                f"{self.seat_list[seat].name} recycled the blanks (once per game).",
                kind="recycle",
                seat=seat,
            )

    def yield_game(self, client_id: str) -> None:
        with self.lock:
            state = self._require_state()
            seat = self._seat_of(client_id)
            state.yield_game(seat)
            self._notice(f"{self.seat_list[seat].name} yielded the match.", kind="yield", seat=seat)
            if state.game_over:
                self._finish()

    def hint(self, client_id: str) -> list[dict]:
        with self.lock:
            if not self.allow_hints:
                raise RulesError("Hints are switched off for this match.")
            state = self._require_state()
            seat = self._seat_of(client_id)
            if state.current != seat:
                raise RulesError("It is not your turn.")
            board = state.board.clone()
            rack = list(state.players[seat].rack)
            bag = list(state.bag)
            my_score = state.players[seat].score
            opp_score = max(p.score for p in state.players if p.seat != seat)
            level = 5
        engine = shared_engine(self.dawg, strategy_lexicon(self.lexicon_name))
        moves = engine.moves(board.grid_string(), rack, bag, my_score, opp_score, level=level, seconds=5, top=3)
        return [
            {
                "word": move.word,
                "score": move.score,
                "row": int(move.get("row", 0)),
                "col": int(move.get("col", 0)),
                "horiz": int(move.get("horiz", 0)),
                "cells": [list(cell) for cell in move.placements],
            }
            for move in moves
        ]

    # ------------------------------------------------------------------ clocks
    def _reset_clock(self) -> None:
        self._deadline = time.monotonic() + self.turn_seconds
        if self.state:
            self._turn_marker = (self.state.turn, self.state.current)
            self._bot_marker = None
            self.state.players[self.state.current].time_left = float(self.turn_seconds)

    def _turn_remaining(self) -> float:
        return max(0.0, self._deadline - time.monotonic())

    def _loop(self) -> None:
        while not self._stop.wait(0.08):
            try:
                with self.lock:
                    if self.phase in ("lobby", "playing"):
                        self._expire_away()
                    if self.phase != "playing" or self.state is None:
                        continue
                    state = self.state
                    if state.game_over:
                        self._finish()
                        continue
                    marker = (state.turn, state.current)
                    if marker != self._turn_marker:
                        self._reset_clock()
                        continue

                    remaining = self._turn_remaining()
                    state.players[state.current].time_left = remaining

                    if remaining <= 0:
                        seat = state.current
                        try:
                            state.pass_turn(seat, timed_out=True)
                        except RulesError:
                            continue
                        self._notice(
                            f"{self.seat_list[seat].name} ran out of time - turn lost.",
                            kind="timeout",
                            seat=seat,
                        )
                        if state.game_over:
                            self._finish()
                        continue

                    seat = state.current
                    if self.seat_list[seat].is_bot and self._bot_marker != marker:
                        self._bot_marker = marker
                        self._start_bot(seat, marker)
            except Exception:
                continue

    def _start_bot(self, seat: int, marker: tuple[int, int]) -> None:
        state = self.state
        assert state is not None
        player = state.players[seat]
        board = state.board.clone()
        rack = list(player.rack)
        bag = list(state.bag)
        my_score = player.score
        opp_score = max(p.score for p in state.players if p.seat != seat)
        level = self.seat_list[seat].level

        def run() -> None:
            delay = 0.6 + self._rng.random() * 0.8
            time.sleep(delay)
            action, payload = choose_bot_action(
                board, rack, bag, my_score, opp_score, level, self.lexicon,
                engine=shared_engine(self.dawg, strategy_lexicon(self.lexicon_name)),
                rng=self._rng,
            )
            with self.lock:
                if self._closed or self.phase != "playing" or self.state is None:
                    return
                if (self.state.turn, self.state.current) != marker:
                    return
                try:
                    if action == "play":
                        self.state.play(seat, payload)  # type: ignore[arg-type]
                        result = self.state.last_play
                        if result:
                            words = ", ".join(f"{word} ({score})" for word, score in result.words)
                            self._notice(
                                f"{self.seat_list[seat].name} played {words} for {result.score}.",
                                kind="play",
                                seat=seat,
                            )
                    elif action == "exchange":
                        self.state.exchange(seat, payload)  # type: ignore[arg-type]
                        self._notice(
                            f"{self.seat_list[seat].name} exchanged tiles.",
                            kind="exchange",
                            seat=seat,
                        )
                    else:
                        self.state.pass_turn(seat)
                        self._notice(f"{self.seat_list[seat].name} passed.", kind="pass", seat=seat)
                except RulesError as exc:
                    self.last_error = f"bot move rejected: {exc} cells={payload}"
                    try:
                        self.state.pass_turn(seat)
                    except RulesError:
                        return
                if self.state.game_over:
                    self._finish()

        self._bot_thread = threading.Thread(target=run, daemon=True)
        self._bot_thread.start()

    def _finish(self) -> None:
        if self.phase == "finished":
            return
        self.phase = "finished"
        if self.state is not None:
            self._notice(self.state.result_message or "Game over.", kind="system")

    # --------------------------------------------------------------- analysis
    def analyse(self, client_id: str, emit) -> None:
        """Review this player's moves with Quackle and stream the results back."""
        with self.lock:
            state = self.state
            if state is None:
                raise RulesError("No game to analyse.")
            if not state.game_over:
                raise RulesError("Finish the match before analysing it.")
            seat = self._seat_of(client_id)
            if self._analysis_running:
                raise RulesError("An analysis is already running.")
            records = [record for record in state.history if record.kind == "play" and record.seat == seat]
            name = self.seat_list[seat].name
            dawg = self.dawg
            self._analysis_running = True

        if not records:
            self._analysis_running = False
            emit({"type": "analysis", "phase": "done", "data": {
                "seat": seat, "name": name, "moves": [],
                "summary": {"count": 0, "average_loss": 0.0, "rating": "-",
                            "best": 0, "good": 0, "inaccuracy": 0, "mistake": 0, "blunder": 0},
            }})
            return

        thread = threading.Thread(
            target=self._run_analysis,
            args=(seat, name, records, dawg, emit),
            daemon=True,
        )
        thread.start()

    def _run_analysis(self, seat: int, name: str, records, dawg: str, emit) -> None:
        engine = shared_engine(dawg, strategy_lexicon(self.lexicon_name))
        total = len(records)
        rows: list[dict] = []
        try:
            for index, record in enumerate(records, start=1):
                if self._closed:
                    return
                my_score = record.scores_before[seat] if seat < len(record.scores_before) else 0
                others = [score for index2, score in enumerate(record.scores_before) if index2 != seat]
                opp_score = max(others) if others else 0

                best_move = None
                try:
                    found = engine.static_moves(
                        record.board_before, record.rack_before, record.bag_before,
                        my_score, opp_score, top=1,
                    )
                    best_move = found[0] if found else None
                except Exception:
                    best_move = None

                played = None
                pattern_info = main_word_pattern(record.board_before, record.cells)
                if pattern_info:
                    row, col, horizontal, pattern = pattern_info
                    try:
                        played = engine.evaluate(
                            record.board_before, record.rack_before, record.bag_before,
                            my_score, opp_score, row, col, horizontal, pattern,
                        )
                    except Exception:
                        played = None

                # Both sides use Quackle's static evaluation, so the losses compare
                # like with like: points, leave value and board position.
                best_equity = best_move.equity if best_move is not None else None
                best_score = best_move.score if best_move is not None else None
                best_word = best_move.word if best_move is not None else None
                played_equity = played.get("equity") if played else None
                if best_equity is not None and played_equity is not None:
                    loss = max(0.0, best_equity - played_equity)
                else:
                    loss = None

                rows.append({
                    "turn": record.turn,
                    "played": record.detail,
                    "played_score": record.score,
                    "best": best_word if best_word is not None else "?",
                    "best_score": best_score,
                    "best_equity": round(best_equity, 2) if best_equity is not None else None,
                    "played_equity": round(played_equity, 2) if played_equity is not None else None,
                    "loss": round(loss, 2) if loss is not None else None,
                    "verdict": classify(loss) if loss is not None else "Unknown",
                })
                emit({"type": "analysis", "phase": "progress", "done": index, "total": total, "seat": seat})

            scored = [row["loss"] for row in rows if row["loss"] is not None]
            average = sum(scored) / len(scored) if scored else 0.0
            counts = {"Best": 0, "Good": 0, "Inaccuracy": 0, "Mistake": 0, "Blunder": 0}
            for row in rows:
                if row["verdict"] in counts:
                    counts[row["verdict"]] += 1
            summary = {
                "count": len(rows),
                "average_loss": round(average, 2),
                "rating": estimate_rating(average),
                "best": counts["Best"],
                "good": counts["Good"],
                "inaccuracy": counts["Inaccuracy"],
                "mistake": counts["Mistake"],
                "blunder": counts["Blunder"],
                "best_moves": sum(1 for row in rows if row["verdict"] == "Best"),
            }
            emit({"type": "analysis", "phase": "done", "data": {
                "seat": seat, "name": name, "moves": rows, "summary": summary,
            }})
        except Exception as exc:
            emit({"type": "analysis", "phase": "error", "message": str(exc)})
        finally:
            self._analysis_running = False

    # ---------------------------------------------------------------- notices
    def _notice(self, text: str, kind: str = "info", seat: int | None = None) -> None:
        self._notices.append(
            {"id": self._notice_id, "text": text, "kind": kind, "seat": seat}
        )
        self._notice_id += 1
        if len(self._notices) > 60:
            self._notices = self._notices[-60:]

    # --------------------------------------------------------------- snapshot
    def snapshot(self, client_id: str | None = None) -> dict:
        with self.lock:
            viewer = None
            if client_id is not None and client_id in self.observers:
                client_id = None  # observers never see a rack
            if client_id is not None:
                for index, seat in enumerate(self.seat_list):
                    if seat.client_id == client_id:
                        viewer = index
                        break
            data = {
                "phase": self.phase,
                "seats": [seat.public() for seat in self.seat_list],
                "settings": {
                    "turn_seconds": self.turn_seconds,
                    "allow_blank_recycle": self.allow_blank_recycle,
                    "max_seats": self.max_seats,
                    "lexicon": self.lexicon_name,
                    "lexicon_label": lexicon_label(self.lexicon_name),
                    "allow_hints": self.allow_hints,
                    "bingo_bonus": self.bingo_bonus,
                    "end_after_six_scoreless": self.end_after_six_scoreless,
                    "minimum_word_length": self.minimum_word_length,
                },
                "viewer": viewer,
                "server_now": time.time(),
                "address": self.address,
                "notices": self._notices[-25:],
                "observers": list(self.observers.values()),
                "state": None,
            }
            if self.state is not None:
                remaining = self._turn_remaining() if self.phase == "playing" else 0.0
                data["state"] = self.state.snapshot(viewer)
                data["turn_remaining"] = round(remaining, 2)
                if viewer is not None and self.phase == "playing":
                    data["can_recycle_blanks"] = self.state.blank_available_to(viewer)
            return data

    def close(self) -> None:
        self._closed = True
        self._stop.set()
