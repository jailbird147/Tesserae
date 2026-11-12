"""Game rules: racks, bag, turns, scoring and end of game."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .board import Board, PlayError, PlayResult
from .lexicon import Lexicon
from .tiles import LETTER_VALUES, RACK_SIZE, full_bag


@dataclass
class PlayerState:
    name: str
    is_bot: bool = False
    level: int = 3
    rack: list[str] = field(default_factory=list)
    score: int = 0
    time_left: float = 120.0
    blanks_recycled: bool = False
    connected: bool = True
    yielded: bool = False
    seat: int = 0
    wins: int = 0

    def public(self, reveal_rack: bool) -> dict:
        data = {
            "name": self.name,
            "seat": self.seat,
            "is_bot": self.is_bot,
            "level": self.level,
            "score": self.score,
            "tiles_left": len(self.rack),
            "time_left": round(self.time_left, 2),
            "blanks_recycled": self.blanks_recycled,
            "connected": self.connected,
            "yielded": self.yielded,
        }
        if reveal_rack:
            data["rack"] = list(self.rack)
        return data


@dataclass
class TurnRecord:
    seat: int
    name: str
    kind: str          # play, exchange, pass, recycle, yield, timeout
    detail: str = ""
    score: int = 0
    turn: int = 0
    # Snapshot taken before the move, used for post-game Quackle analysis.
    cells: list[tuple[int, int, str, bool]] = field(default_factory=list)
    rack_before: list[str] = field(default_factory=list)
    board_before: str = ""
    bag_before: str = ""
    scores_before: list[int] = field(default_factory=list)


class RulesError(Exception):
    pass


class GameState:
    def __init__(
        self,
        names: list[str],
        *,
        bots: list[bool] | None = None,
        levels: list[int] | None = None,
        turn_seconds: int = 120,
        allow_blank_recycle: bool = True,
        lexicon: Lexicon | None = None,
        rng: random.Random | None = None,
        bingo_bonus: bool = True,
        end_after_six_scoreless: bool = True,
        minimum_word_length: int = 0,
    ) -> None:
        if not 2 <= len(names) <= 4:
            raise RulesError("Tessera needs two to four players.")
        self.rng = rng or random.Random()
        self.lexicon = lexicon
        self.turn_seconds = turn_seconds
        self.allow_blank_recycle = allow_blank_recycle
        self.bingo_bonus = bingo_bonus
        self.end_after_six_scoreless = end_after_six_scoreless
        self.minimum_word_length = minimum_word_length

        bots = bots or [False] * len(names)
        levels = levels or [3] * len(names)

        self.players: list[PlayerState] = []
        for i, name in enumerate(names):
            self.players.append(
                PlayerState(
                    name=name,
                    is_bot=bots[i],
                    level=levels[i],
                    time_left=float(turn_seconds),
                    seat=i,
                )
            )

        self.board = Board()
        self.bag: list[str] = full_bag()
        self.rng.shuffle(self.bag)
        self.turn = 1
        self.current = 0
        self.scoreless_turns = 0
        self.game_over = False
        self.result_message = ""
        self.history: list[TurnRecord] = []
        self.last_play: PlayResult | None = None
        self.last_words: list[str] = []
        self.last_cells: list[tuple[int, int]] = []
        self.pending_events: list[dict] = []

        for player in self.players:
            self._draw_to(player, RACK_SIZE)

    # ------------------------------------------------------------------ helpers
    def _draw_to(self, player: PlayerState, target: int) -> None:
        while len(player.rack) < target and self.bag:
            player.rack.append(self.bag.pop())

    def _next_player(self) -> None:
        if self.game_over:
            return
        for _ in range(len(self.players)):
            self.current = (self.current + 1) % len(self.players)
            if not self.players[self.current].yielded:
                break
        self.turn += 1

    def player(self, seat: int) -> PlayerState:
        return self.players[seat]

    def current_player(self) -> PlayerState:
        return self.players[self.current]

    def bag_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for letter in self.bag:
            counts[letter] = counts.get(letter, 0) + 1
        return counts

    def blank_available_to(self, seat: int) -> bool:
        player = self.players[seat]
        return (
            self.allow_blank_recycle
            and not player.blanks_recycled
            and "?" in player.rack
            and bool(self.bag)
            and not self.game_over
        )

    def _rack_worth(self, player: PlayerState) -> int:
        return sum(LETTER_VALUES.get(letter, 0) for letter in player.rack)

    # ------------------------------------------------------------------- moves
    def play(self, seat: int, cells: list[tuple[int, int, str, bool]]) -> PlayResult:
        self._require_turn(seat)
        if not cells:
            raise RulesError("Select at least one tile to play.")

        placements = {}
        used: list[str] = []
        for row, col, letter, blank in cells:
            letter = letter.upper()
            if letter not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                raise RulesError("Pick a letter for the blank.")
            placements[(row, col)] = (letter, bool(blank))
            used.append("?" if blank else letter)

        need = list(used)
        for letter in need:
            if letter not in self.players[seat].rack:
                raise RulesError(f"You do not have {'a blank' if letter == '?' else letter}.")

        try:
            result = self.board.score_play(
                placements, self.lexicon,
                bingo_bonus=self.bingo_bonus,
                minimum_word_length=self.minimum_word_length,
            )
        except PlayError as exc:
            raise RulesError(str(exc)) from exc

        record = TurnRecord(
            seat=seat,
            name=self.players[seat].name,
            kind="play",
            detail=" ".join(word for word, _ in result.words),
            score=result.score,
            turn=self.turn,
            cells=[(row, col, letter, blank) for row, col, letter, blank in cells],
            rack_before=list(self.players[seat].rack),
            board_before=self.board.grid_string(),
            bag_before="".join(self.bag),
            scores_before=[p.score for p in self.players],
        )

        for letter in used:
            self.players[seat].rack.remove(letter)
        self.board.apply(result.placements)
        self.players[seat].score += result.score
        self._draw_to(self.players[seat], RACK_SIZE)

        self.last_play = result
        self.last_words = [word for word, _ in result.words]
        self.last_cells = list(result.placements.keys())
        self.scoreless_turns = 0 if result.score > 0 else self.scoreless_turns + 1
        self.history.append(record)
        self._reset_clock(seat)
        self._after_turn(seat)
        return result

    def exchange(self, seat: int, letters: list[str]) -> None:
        self._require_turn(seat)
        player = self.players[seat]
        letters = [letter.upper() if letter != "?" else "?" for letter in letters]
        if not letters:
            raise RulesError("Choose tiles to exchange.")
        if len(self.bag) < RACK_SIZE:
            raise RulesError("You cannot exchange until there are seven tiles in the bag.")
        remaining = list(player.rack)
        for letter in letters:
            if letter not in remaining:
                raise RulesError(f"You do not have {letter}.")
            remaining.remove(letter)
        for letter in letters:
            self.bag.append(letter)
        self.rng.shuffle(self.bag)
        player.rack = remaining
        self._draw_to(player, RACK_SIZE)
        self.scoreless_turns += 1
        self.history.append(
            TurnRecord(
                seat=seat,
                name=player.name,
                kind="exchange",
                detail=f"exchanged {len(letters)}",
                turn=self.turn,
            )
        )
        self._reset_clock(seat)
        self._after_turn(seat)

    def pass_turn(self, seat: int, timed_out: bool = False) -> None:
        self._require_turn(seat)
        player = self.players[seat]
        self.scoreless_turns += 1
        self.history.append(
            TurnRecord(
                seat=seat,
                name=player.name,
                kind="timeout" if timed_out else "pass",
                detail="ran out of time" if timed_out else "passed",
                turn=self.turn,
            )
        )
        self._reset_clock(seat)
        self._after_turn(seat)

    def recycle_blanks(self, seat: int) -> None:
        self._require_turn(seat)
        player = self.players[seat]
        if not self.allow_blank_recycle:
            raise RulesError("Blank recycling is switched off for this game.")
        if player.blanks_recycled:
            raise RulesError("You can only recycle the blanks once per game.")
        blanks = player.rack.count("?")
        if blanks == 0:
            raise RulesError("You do not have a blank to recycle.")
        if not self.bag:
            raise RulesError("The bag is empty.")

        for _ in range(blanks):
            player.rack.remove("?")
            self.bag.append("?")
        self.rng.shuffle(self.bag)
        self._draw_to(player, RACK_SIZE)
        player.blanks_recycled = True
        self.history.append(
            TurnRecord(
                seat=seat,
                name=player.name,
                kind="recycle",
                detail="recycled the blanks",
                turn=self.turn,
            )
        )
        self.pending_events.append(
            {"kind": "toast", "text": f"{player.name} recycled the blanks.", "seat": seat}
        )

    def yield_game(self, seat: int) -> None:
        if self.game_over:
            return
        player = self.players[seat]
        player.yielded = True
        self.history.append(
            TurnRecord(
                seat=seat,
                name=player.name,
                kind="yield",
                detail="yielded the match",
                turn=self.turn,
            )
        )
        alive = [p for p in self.players if not p.yielded]
        if len(alive) <= 1:
            self._finish(winner=alive[0] if alive else None, yielded_by=player)
        else:
            self.pending_events.append(
                {"kind": "toast", "text": f"{player.name} yielded.", "seat": seat}
            )
            if self.current == seat:
                self._next_player()

    def set_connected(self, seat: int, connected: bool) -> None:
        if 0 <= seat < len(self.players):
            self.players[seat].connected = bool(connected)

    def forfeit(self, seat: int) -> None:
        """A player who never came back: out of the match, like a yield."""
        if self.game_over or not (0 <= seat < len(self.players)):
            return
        player = self.players[seat]
        if player.yielded:
            return
        player.yielded = True
        player.connected = False
        self.history.append(
            TurnRecord(
                seat=seat,
                name=player.name,
                kind="forfeit",
                detail="did not reconnect",
                turn=self.turn,
            )
        )
        alive = [p for p in self.players if not p.yielded]
        if len(alive) <= 1:
            self._finish(winner=alive[0] if alive else None, yielded_by=player, reason="forfeit")
        else:
            self.pending_events.append(
                {"kind": "toast", "text": f"{player.name} forfeited.", "seat": seat}
            )
            if self.current == seat:
                self._next_player()

    def _require_turn(self, seat: int) -> None:
        if self.game_over:
            raise RulesError("The game is over.")
        if seat != self.current:
            raise RulesError("It is not your turn.")
        if self.players[seat].yielded:
            raise RulesError("You yielded this match.")

    def _reset_clock(self, seat: int) -> None:
        self.players[seat].time_left = float(self.turn_seconds)

    # -------------------------------------------------------------- end of game
    def _after_turn(self, seat: int) -> None:
        player = self.players[seat]
        if not player.rack and not self.bag:
            self._finish(winner=player)
            return
        if self.end_after_six_scoreless and self.scoreless_turns >= 6:
            self._finish(winner=None)
            return
        self._next_player()

    def _finish(self, winner: PlayerState | None = None, yielded_by: PlayerState | None = None,
                reason: str = "yield") -> None:
        self.game_over = True
        if winner is not None and not winner.rack and not self.bag:
            # Going out: collect the value of everyone else's leftover tiles.
            bonus = 0
            for player in self.players:
                if player is winner:
                    continue
                worth = self._rack_worth(player)
                player.score -= worth
                bonus += worth
            winner.score += bonus
        else:
            for player in self.players:
                player.score -= self._rack_worth(player)

        alive = [p for p in self.players if not p.yielded]
        if yielded_by is not None:
            best = max((p.score for p in alive), default=0)
            leaders = [p for p in alive if p.score == best]
            if reason == "forfeit":
                opening = f"{yielded_by.name} did not reconnect and forfeits."
            else:
                opening = f"{yielded_by.name} yielded the match."
            self.result_message = (
                opening if len(leaders) == 1 else "The match ended with a tie."
            )
            if leaders:
                self.result_message += f" {leaders[0].name} takes it."
        elif winner is not None:
            leaders = [winner]
            self.result_message = f"{winner.name} went out and wins."
        else:
            best = max((p.score for p in alive), default=0)
            leaders = [p for p in alive if p.score == best]
            if not leaders:
                self.result_message = "Six scoreless turns - the game ends."
            elif len(leaders) > 1:
                self.result_message = "Six scoreless turns - the game ends in a tie."
            else:
                self.result_message = f"Six scoreless turns - {leaders[0].name} wins."
        for player in leaders:
            player.wins += 1

    # ---------------------------------------------------------------- snapshot
    def snapshot(self, viewer: int | None) -> dict:
        players = []
        for player in self.players:
            players.append(player.public(reveal_rack=(viewer is not None and player.seat == viewer)))
        return {
            "players": players,
            "board": [[list(cell) if cell else None for cell in row] for row in self.board.grid],
            "bag": len(self.bag),
            "turn": self.turn,
            "current": self.current if not self.game_over else None,
            "game_over": self.game_over,
            "result": self.result_message,
            "turn_seconds": self.turn_seconds,
            "allow_blank_recycle": self.allow_blank_recycle,
            "history": [
                {
                    "seat": record.seat,
                    "name": record.name,
                    "kind": record.kind,
                    "detail": record.detail,
                    "score": record.score,
                    "turn": record.turn,
                }
                for record in self.history[-40:]
            ],
            "last_words": list(self.last_words),
            "last_cells": [list(cell) for cell in self.last_cells],
            "word_count": len(self.lexicon.words) if self.lexicon else 0,
        }
