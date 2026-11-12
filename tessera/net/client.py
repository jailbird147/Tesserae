"""Network client used by the game UI (also for local play)."""

from __future__ import annotations

import socket
import threading
import time

from .protocol import LineReader, send_line

# The server holds a seat for sixty seconds; retry for about as long.
RECONNECT_WINDOW = 60.0
RECONNECT_INTERVAL = 2.0


class NetClient:
    def __init__(self) -> None:
        self.socket: socket.socket | None = None
        self.client_id = ""
        self.token = ""
        self.seat: int | None = None
        self.is_host = False
        self.observer = False
        self.snapshot: dict | None = None
        self.analysis: dict | None = None
        self.connected = False
        self.errors: list[str] = []
        self.hints: list[dict] = []
        self._lock = threading.RLock()
        self._reader: threading.Thread | None = None
        self._welcome = threading.Event()
        self.connect_error = ""

        # Where we came from, so a dropped connection can be picked up again.
        self.host = ""
        self.port = 0
        self.name = ""
        self.observe = False
        self.auto_reconnect = True
        self.reconnecting = False
        self.reconnect_attempts = 0
        self.reconnect_refused = ""
        self.gave_up = False
        self._closed = False

    # ------------------------------------------------------------------ connect
    def connect(self, host: str, port: int, name: str, timeout: float = 6.0, observe: bool = False) -> bool:
        self.close()
        self.connect_error = ""
        self.host, self.port, self.name, self.observe = host, port, name, observe
        self._closed = False
        self.gave_up = False
        self.reconnecting = False
        self.reconnect_attempts = 0
        self.reconnect_refused = ""
        self.token = ""
        self.client_id = ""
        with self._lock:
            self.errors = []
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.settimeout(None)
        except OSError as exc:
            self.connect_error = f"Could not reach {host}:{port} - {exc}"
            return False

        if not self._handshake(sock, {"type": "join", "name": name, "observe": observe}, timeout):
            self.connect_error = self.connect_error or "The server did not answer."
            self.close()
            return False
        return self.connected

    def connect_rejoin(self, host: str, port: int, client_id: str, token: str,
                       timeout: float = 6.0) -> bool:
        """Take a held seat back with the token the server gave out."""
        self.close()
        self.connect_error = ""
        self.host, self.port = host, port
        self.client_id, self.token = client_id, token
        self._closed = False
        self.reconnect_refused = ""
        with self._lock:
            self.errors = []
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.settimeout(None)
        except OSError as exc:
            self.connect_error = f"Could not reach {host}:{port} - {exc}"
            return False
        payload = {"type": "rejoin", "client_id": client_id, "token": token}
        if not self._handshake(sock, payload, timeout):
            self.connect_error = self.connect_error or "The server did not answer."
            return False
        return self.connected

    def _handshake(self, sock: socket.socket, payload: dict, timeout: float) -> bool:
        self._welcome.clear()
        self.socket = sock
        self._reader = threading.Thread(target=self._read_loop, args=(sock,), daemon=True)
        self._reader.start()
        try:
            send_line(sock, payload)
        except OSError:
            return False
        if not self._welcome.wait(timeout):
            self.connect_error = "The server did not answer."
            return False
        if not self.connected:
            # The server refused before saying hello: use its own words.
            with self._lock:
                if self.errors:
                    self.connect_error = self.errors[-1]
        return self.connected

    def _read_loop(self, sock: socket.socket) -> None:
        reader = LineReader(sock)
        try:
            while True:
                message = reader.read()
                if message is None:
                    break
                kind = message.get("type")
                if kind == "welcome":
                    self.client_id = message.get("client_id", "")
                    self.token = str(message.get("token", ""))
                    self.seat = message.get("seat")
                    self.is_host = bool(message.get("is_host"))
                    self.observer = bool(message.get("observer"))
                    self.snapshot = message.get("state")
                    self.connected = True
                    self._welcome.set()
                elif kind == "state":
                    self.snapshot = message.get("state")
                elif kind == "error":
                    text = str(message.get("message", "error"))
                    with self._lock:
                        self.errors.append(text)
                    if message.get("fatal"):
                        self.reconnect_refused = text
                elif kind == "hint":
                    with self._lock:
                        self.hints.append(message)
                elif kind == "analysis":
                    self.analysis = message
        except OSError:
            pass
        finally:
            if self.socket is sock:
                self.connected = False
                self._welcome.set()
                if not self._closed and self.auto_reconnect and self.token:
                    self._start_reconnect()

    # -------------------------------------------------------------- reconnection
    def _start_reconnect(self) -> None:
        with self._lock:
            if self.reconnecting or self.gave_up or self._closed or not self.token:
                return
            self.reconnecting = True
            self.reconnect_attempts = 0
        threading.Thread(target=self._reconnect_loop, daemon=True).start()

    def _reconnect_loop(self) -> None:
        deadline = time.monotonic() + RECONNECT_WINDOW
        while not self._closed and time.monotonic() < deadline:
            time.sleep(RECONNECT_INTERVAL)
            if self._closed or self.reconnect_refused:
                break
            self.reconnect_attempts += 1
            if self._try_reconnect():
                return
        with self._lock:
            self.reconnecting = False
            if not self.connected:
                self.gave_up = True

    def _try_reconnect(self) -> bool:
        try:
            sock = socket.create_connection((self.host, self.port), timeout=6.0)
            sock.settimeout(None)
        except OSError:
            return False
        payload = {"type": "rejoin", "client_id": self.client_id, "token": self.token}
        if not self._handshake(sock, payload, 8.0) or not self.connected:
            try:
                sock.close()
            except OSError:
                pass
            return False
        with self._lock:
            self.reconnecting = False
            self.gave_up = False
        return True

    @property
    def reconnect_note(self) -> str:
        if self.reconnect_refused:
            return self.reconnect_refused
        if self.reconnecting:
            return f"Reconnecting... ({self.reconnect_attempts})"
        if self.gave_up:
            return "Could not get back to the game."
        return ""

    # ------------------------------------------------------------------ output
    def _send(self, payload: dict) -> None:
        if self.socket is None:
            return
        try:
            send_line(self.socket, payload)
        except OSError:
            self.connected = False

    def play(self, cells: list[tuple[int, int, str, bool]]) -> None:
        self._send({"type": "action", "action": "play", "cells": [list(cell) for cell in cells]})

    def exchange(self, letters: list[str]) -> None:
        self._send({"type": "action", "action": "exchange", "letters": list(letters)})

    def pass_turn(self) -> None:
        self._send({"type": "action", "action": "pass"})

    def yield_game(self) -> None:
        self._send({"type": "action", "action": "yield"})

    def recycle_blanks(self) -> None:
        self._send({"type": "action", "action": "recycle"})

    def ask_hint(self) -> None:
        self._send({"type": "hint"})

    def ask_analysis(self) -> None:
        self.analysis = {"type": "analysis", "phase": "starting"}
        self._send({"type": "analyse"})

    def host_command(self, **payload) -> None:
        payload["type"] = "host"
        self._send(payload)

    # ------------------------------------------------------------------- input
    def drain_errors(self) -> list[str]:
        with self._lock:
            errors, self.errors = self.errors, []
        return errors

    def drain_hints(self) -> list[dict]:
        with self._lock:
            hints, self.hints = self.hints, []
        return hints

    def close(self) -> None:
        self._closed = True
        self.connected = False
        self.reconnecting = False
        if self.socket is not None:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.socket.close()
            except OSError:
                pass
        self.socket = None
