"""Bridge to the local Quackle engine (qengine.exe)."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Move(dict):
    """A move reported by Quackle."""

    @property
    def placements(self) -> list[tuple[int, int, str, bool]]:
        row = int(self.get("row", 0))
        col = int(self.get("col", 0))
        horizontal = bool(int(self.get("horiz", 0)))
        pattern = self.get("tiles", "")
        cells: list[tuple[int, int, str, bool]] = []
        r, c = row, col
        for char in pattern:
            if char == ".":
                pass
            elif char.islower():
                cells.append((r, c, char.upper(), True))
            else:
                cells.append((r, c, char.upper(), False))
            if horizontal:
                c += 1
            else:
                r += 1
        return cells

    @property
    def word(self) -> str:
        return str(self.get("word", ""))

    @property
    def score(self) -> int:
        try:
            return int(self.get("score", 0))
        except (TypeError, ValueError):
            return 0

    @property
    def equity(self) -> float:
        try:
            return float(self.get("equity", 0.0))
        except (TypeError, ValueError):
            return 0.0


class EngineError(Exception):
    pass


def engine_path(path: str) -> str:
    """Absolute path the engine can be given on its command line.

    The line protocol splits on spaces, so a path with a space in it (a Windows
    user folder such as C:\\Users\\Ann Smith) is shortened to its 8.3 form.
    """
    full = os.path.abspath(path)
    if os.name != "nt" or " " not in full:
        return full
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(full, buffer, len(buffer)):
            return buffer.value
    except Exception:
        pass
    return full


class QuackleEngine:
    """One engine process, serialised with a lock."""

    def __init__(self, root: str | None = None, dawg: str | None = None,
                 lexicon: str | None = None) -> None:
        from .lexicon import default_lexicon, lexicon_dawg, strategy_lexicon

        self.root = root or ROOT
        self.exe = os.path.join(self.root, "engine", "qengine.exe")
        # Default to whichever list this build actually has (the Store build
        # ships ENABLE, not the Collins lists).
        self.dawg = engine_path(dawg or lexicon_dawg(default_lexicon()))
        # Quackle names its strategy data after a lexicon; imported word lists
        # reuse the CSW24 strategy files.
        self.lexicon = lexicon or strategy_lexicon(default_lexicon())
        self._process: subprocess.Popen | None = None
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self.last_error = ""

    # -------------------------------------------------------------- lifecycle
    def available(self) -> bool:
        return os.path.exists(self.exe)

    def _start(self) -> None:
        if not self.available():
            raise EngineError("Quackle engine executable is missing.")
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self._process = subprocess.Popen(
            [self.exe],
            cwd=self.root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            creationflags=flags,
        )
        self._reader = threading.Thread(target=self._read_loop, args=(self._process,), daemon=True)
        self._reader.start()

        reply = self._request_locked(
            f"INIT data=data dawg={self.dawg} lexicon={self.lexicon}", timeout=120
        )
        if not any(line.startswith("OK") for line in reply):
            self._stop_locked()
            raise EngineError(f"Quackle could not load {self.dawg}.")

    def _read_loop(self, process: subprocess.Popen) -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                self._queue.put(line.rstrip("\r\n"))
        except Exception:
            pass

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.poll() is None:
                if process.stdin:
                    process.stdin.write("QUIT\n")
                    process.stdin.flush()
                process.wait(timeout=1.0)
        except Exception:
            pass
        finally:
            try:
                process.kill()
            except Exception:
                pass
            self._drain()

    def _drain(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def ensure_started(self) -> None:
        with self._lock:
            self._ensure_locked()

    def _ensure_locked(self) -> None:
        if self._process is None or self._process.poll() is not None:
            self._stop_locked()
            self._start()

    # ---------------------------------------------------------------- request
    def _request_locked(self, command: str, timeout: float = 30.0) -> list[str]:
        """Send a command. The caller must hold self._lock."""
        if self._process is None or self._process.poll() is not None:
            self._stop_locked()
            self._start()
        assert self._process is not None
        assert self._process.stdin is not None
        self._drain()
        try:
            self._process.stdin.write(command + "\n")
            self._process.stdin.flush()
        except Exception as exc:  # engine died
            self.last_error = str(exc)
            self._stop_locked()
            return []

        lines: list[str] = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.last_error = "engine timed out"
                self._stop_locked()
                return lines
            try:
                line = self._queue.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if self._process is None or self._process.poll() is not None:
                    self._stop_locked()
                    return lines
                continue
            if line.startswith("MOVE"):
                lines.append(line)
            elif line.startswith("SCORE"):
                lines.append(line)
                return lines
            elif line.startswith("END") or line.startswith("BYE"):
                return lines
            elif line.startswith("OK"):
                lines.append(line)
                return lines
            elif line.startswith("ERR"):
                self.last_error = line
                return []
            # anything else is library chatter; ignore it

    # ----------------------------------------------------------------- public
    def moves(
        self,
        board_grid: str,
        rack: list[str] | str,
        bag: list[str] | str,
        my_score: int,
        opp_score: int,
        level: int,
        seconds: float,
        top: int = 12,
    ) -> list[Move]:
        rack_text = "".join(rack) if not isinstance(rack, str) else rack
        bag_text = "".join(bag) if not isinstance(bag, str) else bag
        command = (
            f"MOVES board={board_grid} rack={rack_text} bag={bag_text} "
            f"my={my_score} opp={opp_score} level={level} "
            f"top={top} secs={max(1, int(round(seconds)))}"
        )
        with self._lock:
            self._ensure_locked()
            lines = self._request_locked(command, timeout=max(20.0, seconds * 4 + 30))
        out: list[Move] = []
        for line in lines:
            fields = {}
            for token in line.split()[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    fields[key] = value
            if fields.get("action") == "play":
                out.append(Move(fields))
        return out

    def evaluate(
        self,
        board_grid: str,
        rack: list[str] | str,
        bag: list[str] | str,
        my_score: int,
        opp_score: int,
        row: int,
        col: int,
        horizontal: bool,
        pattern: str,
    ) -> dict:
        """Score and value one specific move in the given position."""
        rack_text = "".join(rack) if not isinstance(rack, str) else rack
        bag_text = "".join(bag) if not isinstance(bag, str) else bag
        command = (
            f"EVAL board={board_grid} rack={rack_text} bag={bag_text} "
            f"my={my_score} opp={opp_score} row={row} col={col} "
            f"horiz={1 if horizontal else 0} tiles={pattern}"
        )
        with self._lock:
            self._ensure_locked()
            lines = self._request_locked(command, timeout=15)
        for line in lines:
            if not line.startswith("SCORE"):
                continue
            fields = {}
            for token in line.split()[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    fields[key] = value
            try:
                return {
                    "score": int(float(fields.get("score", 0))),
                    "equity": float(fields.get("equity", 0.0)),
                }
            except ValueError:
                return {}
        return {}

    def static_moves(self, board_grid: str, rack: list[str], bag: list[str], my_score: int,
                     opp_score: int, top: int = 1) -> list[Move]:
        """Moves ranked by Quackle's static evaluation (points + leave + board)."""
        rack_text = "".join(rack) if not isinstance(rack, str) else rack
        bag_text = "".join(bag) if not isinstance(bag, str) else bag
        command = (
            f"STATIC board={board_grid} rack={rack_text} bag={bag_text} "
            f"my={my_score} opp={opp_score} top={max(1, top)}"
        )
        with self._lock:
            self._ensure_locked()
            lines = self._request_locked(command, timeout=60)
        out: list[Move] = []
        for line in lines:
            if not line.startswith("MOVE"):
                continue
            fields = {}
            for token in line.split()[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    fields[key] = value
            if fields.get("action") == "play":
                out.append(Move(fields))
        return out

    def hint(self, board_grid: str, rack: list[str], bag: list[str], my_score: int, opp_score: int, top: int = 3) -> list[Move]:
        return self.moves(board_grid, rack, bag, my_score, opp_score, level=5, seconds=6, top=top)


_shared_engine: QuackleEngine | None = None
_shared_lock = threading.Lock()


def shared_engine(dawg: str | None = None, lexicon: str | None = None) -> QuackleEngine:
    """One engine process for the app, restarted if the word list changes."""
    global _shared_engine
    from .lexicon import default_lexicon, lexicon_dawg, strategy_lexicon

    dawg = engine_path(dawg or lexicon_dawg(default_lexicon()))
    lexicon = lexicon or strategy_lexicon(default_lexicon())
    with _shared_lock:
        if _shared_engine is None:
            _shared_engine = QuackleEngine(dawg=dawg, lexicon=lexicon)
        elif _shared_engine.dawg != dawg or _shared_engine.lexicon != lexicon:
            _shared_engine.stop()
            _shared_engine = QuackleEngine(dawg=dawg, lexicon=lexicon)
        return _shared_engine
