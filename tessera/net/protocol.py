"""Tiny newline-delimited JSON protocol."""

from __future__ import annotations

import json
import socket


def send_line(sock: socket.socket, payload: dict) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
    sock.sendall(data)


class LineReader:
    def __init__(self, sock: socket.socket, buffer_size: int = 65536) -> None:
        self.sock = sock
        self.buffer = b""
        self.buffer_size = buffer_size

    def read(self) -> dict | None:
        while b"\n" not in self.buffer:
            chunk = self.sock.recv(self.buffer_size)
            if not chunk:
                return None
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
