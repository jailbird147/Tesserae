"""Network game server: hosts one Session for up to four players."""

from __future__ import annotations

import hmac
import queue
import socket
import threading
import time
import uuid

from ..rules import RulesError
from ..session import Session
from .protocol import LineReader, send_line


class GameServer:
    def __init__(self, session: Session | None = None, port: int = 0, host: str = "0.0.0.0",
                 tournament=None) -> None:
        self.session = session
        self.tournament = tournament
        self.host = host
        self.port = port
        self.socket: socket.socket | None = None
        self.clients: dict[str, dict] = {}
        self.lock = threading.RLock()
        self.running = False
        self.host_id: str | None = None
        # client_id -> token and name, kept while a drop can still be undone
        self.identities: dict[str, dict] = {}
        self._threads: list[threading.Thread] = []
        self._broadcast_thread: threading.Thread | None = None
        self._accept_thread: threading.Thread | None = None
        self.last_error = ""

    # -------------------------------------------------------------- lifecycle
    def start(self) -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(8)
        self.socket = sock
        self.port = sock.getsockname()[1]
        self.running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._broadcast_thread.start()
        return self.port

    def stop(self) -> None:
        self.running = False
        try:
            if self.socket:
                self.socket.close()
        except OSError:
            pass
        with self.lock:
            for client in list(self.clients.values()):
                try:
                    client["sock"].close()
                except OSError:
                    pass
            self.clients.clear()
            self.identities.clear()
        if self.tournament is not None:
            self.tournament.close()
        if self.session is not None:
            self.session.close()

    # ------------------------------------------------------------------ accept
    def _accept_loop(self) -> None:
        assert self.socket is not None
        while self.running:
            try:
                conn, _addr = self.socket.accept()
            except OSError:
                break
            threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()

    def _client_loop(self, conn: socket.socket) -> None:
        conn.settimeout(None)
        reader = LineReader(conn)
        client_id = uuid.uuid4().hex
        name = ""
        joined = False

        with self.lock:
            self.clients[client_id] = {
                "sock": conn,
                "name": name,
                "queue": queue.Queue(),
                "joined": False,
            }
        writer = threading.Thread(target=self._writer_loop, args=(client_id,), daemon=True)
        writer.start()

        try:
            while self.running:
                message = reader.read()
                if message is None:
                    break
                if not message:
                    continue
                kind = message.get("type")
                if kind in ("join", "rejoin") and not joined:
                    if kind == "rejoin":
                        resume = self._resume(conn, client_id, message)
                        if resume is None:
                            break
                        client_id, seat = resume
                        identity = self.identities[client_id]
                        name = identity["name"]
                    else:
                        name = str(message.get("name", "")).strip() or "Player"
                        observe = bool(message.get("observe"))
                        seat = None
                        try:
                            if self.tournament is not None:
                                if not observe:
                                    self.tournament.join(client_id, name)
                            elif observe:
                                self.session.join_observer(client_id, name)
                            else:
                                seat = self.session.join(name, client_id)
                        except RulesError as exc:
                            self._send(client_id, {"type": "error", "message": str(exc)})
                            self._flush_before_close()
                            break
                        identity = {
                            "name": name,
                            "observer": observe,
                            "token": uuid.uuid4().hex,
                        }
                        with self.lock:
                            self.identities[client_id] = identity
                        if self.host_id is None and not observe:
                            self.host_id = client_id
                    joined = True
                    with self.lock:
                        client = self.clients.get(client_id)
                        if client is not None:
                            client["joined"] = True
                            client["name"] = name
                            client["observer"] = identity["observer"]
                    self._send(client_id, {
                        "type": "welcome",
                        "client_id": client_id,
                        "seat": seat,
                        "observer": identity["observer"],
                        "is_host": self.host_id == client_id,
                        "token": identity["token"],
                        "state": self._snapshot(client_id),
                    })
                    continue
                if not joined:
                    continue
                self._handle(client_id, message)
        except (ConnectionError, OSError):
            pass
        finally:
            still_bound = False
            with self.lock:
                entry = self.clients.get(client_id)
                if entry is not None and entry["sock"] is conn:
                    self.clients.pop(client_id, None)
                    still_bound = True
            if joined and still_bound:
                # Hold the seat for the grace period; identity stays so a
                # rejoin can take it back.
                if self.tournament is not None:
                    self.tournament.mark_away(client_id)
                if self.session is not None:
                    self.session.leave(client_id)
            try:
                conn.close()
            except OSError:
                pass

    def _resume(self, conn: socket.socket, temporary_id: str, message: dict):
        """Re-bind a returning connection to its old client id."""
        client_id = str(message.get("client_id", ""))
        token = str(message.get("token", ""))
        with self.lock:
            identity = self.identities.get(client_id)
        if identity is None or not token or not hmac.compare_digest(identity["token"], token):
            self._send(temporary_id, {
                "type": "error",
                "fatal": True,
                "message": "That game is no longer open for reconnection.",
            })
            self._flush_before_close()
            return None
        with self.lock:
            # The throw-away entry this connection registered on accept.
            self.clients.pop(temporary_id, None)
            old = self.clients.get(client_id)
            if old is not None and old.get("sock") is not None and old["sock"] is not conn:
                try:
                    old["sock"].close()      # the stale connection, if it is still open
                except OSError:
                    pass
            self.clients[client_id] = {
                "sock": conn,
                "name": identity["name"],
                "queue": queue.Queue(),
                "joined": True,
                "observer": identity["observer"],
            }
        threading.Thread(target=self._writer_loop, args=(client_id,), daemon=True).start()
        seat = None
        try:
            if self.tournament is not None:
                if not identity["observer"]:
                    self.tournament.rejoin(client_id)
            elif identity["observer"]:
                if self.session is not None:
                    self.session.join_observer(client_id, identity["name"])
            else:
                seat = self.session.rejoin(client_id)
        except RulesError as exc:
            self._send(client_id, {"type": "error", "fatal": True, "message": str(exc)})
            self._flush_before_close()
            return None
        return client_id, seat

    @staticmethod
    def _flush_before_close() -> None:
        """Give a queued error time to reach a connection we are about to drop."""
        time.sleep(0.6)

    # ------------------------------------------------------------------ writer
    def _writer_loop(self, client_id: str) -> None:
        while self.running:
            with self.lock:
                client = self.clients.get(client_id)
            if client is None:
                return
            try:
                payload = client["queue"].get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                send_line(client["sock"], payload)
            except OSError:
                return

    def _send(self, client_id: str, payload: dict) -> None:
        with self.lock:
            client = self.clients.get(client_id)
        if client is not None:
            client["queue"].put(payload)

    # -------------------------------------------------------------- broadcast
    def _broadcast_loop(self) -> None:
        while self.running:
            time.sleep(0.2)
            with self.lock:
                ids = [cid for cid, info in self.clients.items() if info["joined"]]
            for client_id in ids:
                try:
                    snapshot = self._snapshot(client_id)
                except Exception as exc:  # keep the server alive
                    self.last_error = str(exc)
                    continue
                self._send(client_id, {"type": "state", "state": snapshot, "you": client_id})

    # --------------------------------------------------------------- commands
    def _handle(self, client_id: str, message: dict) -> None:
        kind = message.get("type")
        if kind == "host":
            self._handle_host(client_id, message)
            return
        if kind == "action":
            session = self._active_session()
            if session is None:
                self._send(client_id, {"type": "error", "message": "No match is running."})
                return
            action = message.get("action")
            try:
                if action == "play":
                    cells = [
                        (int(cell[0]), int(cell[1]), str(cell[2]).upper(), bool(cell[3]))
                        for cell in message.get("cells", [])
                    ]
                    session.play(client_id, cells)
                elif action == "exchange":
                    session.exchange(client_id, [str(letter) for letter in message.get("letters", [])])
                elif action == "pass":
                    session.pass_turn(client_id)
                elif action == "yield":
                    session.yield_game(client_id)
                elif action == "recycle":
                    session.recycle_blanks(client_id)
            except RulesError as exc:
                self._send(client_id, {"type": "error", "message": str(exc)})
            except Exception as exc:
                self._send(client_id, {"type": "error", "message": f"Unexpected: {exc}"})
            return
        if kind == "hint":
            session = self._active_session()
            if session is None:
                return
            try:
                moves = session.hint(client_id)
                self._send(client_id, {"type": "hint", "moves": moves})
            except RulesError as exc:
                self._send(client_id, {"type": "error", "message": str(exc)})
            return
        if kind == "analyse":
            session = self._active_session()
            if session is None:
                self._send(client_id, {"type": "analysis", "phase": "error", "message": "No match to analyse."})
                return
            try:
                session.analyse(client_id, lambda payload: self._send(client_id, payload))
            except RulesError as exc:
                self._send(client_id, {"type": "analysis", "phase": "error", "message": str(exc)})
            except Exception as exc:
                self._send(client_id, {"type": "analysis", "phase": "error", "message": str(exc)})

    def _handle_host(self, client_id: str, message: dict) -> None:
        if client_id != self.host_id:
            self._send(client_id, {"type": "error", "message": "Only the host can change the game."})
            return
        action = message.get("action")
        if self.tournament is not None:
            self._handle_tournament_host(client_id, action, message)
            return
        if self.session is None:
            return
        try:
            if action == "settings":
                self.session.set_settings(
                    turn_seconds=message.get("turn_seconds"),
                    allow_blank_recycle=message.get("allow_blank_recycle"),
                    seats=message.get("seats"),
                    lexicon=message.get("lexicon"),
                    allow_hints=message.get("allow_hints"),
                    bingo_bonus=message.get("bingo_bonus"),
                    end_after_six_scoreless=message.get("end_after_six_scoreless"),
                    minimum_word_length=message.get("minimum_word_length"),
                )
            elif action == "add_bot":
                self.session.add_bot(int(message.get("seat", 0)), int(message.get("level", 3)))
            elif action == "remove_bot":
                self.session.remove_bot(int(message.get("seat", 0)))
            elif action == "start":
                self.session.start()
            elif action == "rematch":
                self.session.rematch()
        except RulesError as exc:
            self._send(client_id, {"type": "error", "message": str(exc)})
        except Exception as exc:
            self._send(client_id, {"type": "error", "message": f"Unexpected: {exc}"})

    def _handle_tournament_host(self, client_id: str, action: str, message: dict) -> None:
        tournament = self.tournament
        try:
            if action == "start":
                tournament.start()
            elif action == "add_bot":
                tournament.add_bot(int(message.get("level", 3)))
            elif action == "set_bot_level":
                tournament.set_bot_level(str(message.get("client_id", "")), int(message.get("level", 3)))
            elif action == "remove_participant":
                tournament.remove_participant(str(message.get("client_id", "")))
        except RulesError as exc:
            self._send(client_id, {"type": "error", "message": str(exc)})
        except Exception as exc:
            self._send(client_id, {"type": "error", "message": f"Unexpected: {exc}"})

    def _active_session(self):
        if self.tournament is not None:
            return self.tournament.session
        return self.session

    def _snapshot(self, client_id: str) -> dict:
        if self.tournament is not None:
            return self.tournament.snapshot(client_id)
        if self.session is None:
            return {}
        return self.session.snapshot(client_id)


# --------------------------------------------------------------------- helpers
def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def public_ip(timeout: float = 3.0) -> str:
    import urllib.request

    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as response:
            return response.read().decode("utf-8").strip()
    except Exception:
        return ""
