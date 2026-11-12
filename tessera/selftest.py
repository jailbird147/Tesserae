"""Headless self test, also used to verify the packaged build.

Run with:  Tessera.exe --selftest     (writes %TEMP%\\tessera_selftest.log)
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback


def _log_path() -> str:
    return os.path.join(tempfile.gettempdir(), "tessera_selftest.log")


def run_selftest() -> int:
    lines: list[str] = []

    def say(message: str) -> None:
        lines.append(str(message))
        print(message, flush=True)

    ok = False
    try:
        from .engine import QuackleEngine
        from .lexicon import data_path, default_lexicon, lexicon_names, load_lexicon
        from .ui.app import App

        say(f"frozen={getattr(sys, 'frozen', False)} root={data_path()}")
        say(f"word lists={','.join(lexicon_names())} default={default_lexicon()}")
        lexicon = load_lexicon()
        say(f"lexicon words={len(lexicon)}")
        say(f"engine exists={os.path.exists(data_path('engine', 'qengine.exe'))}")

        engine = QuackleEngine()
        engine.ensure_started()
        moves = engine.moves("." * 225, "AEIRST?", "AEIOULNSTR" * 8, 0, 0, level=1, seconds=1, top=3)
        say(f"engine moves={len(moves)} first={moves[0].word if moves else '-'}")

        app = App()
        app.start_local("SelfTest", [1], 60, True)
        deadline = time.time() + 20
        while time.time() < deadline:
            snapshot = app.client.snapshot if app.client else None
            if snapshot and snapshot.get("state"):
                state = snapshot["state"]
                say(f"game turn={state['turn']} current={state['current']} bag={state['bag']}")
                rack = state["players"][app.client.seat]["rack"]
                say(f"rack={''.join(rack)}")
                break
            time.sleep(0.1)

        # Drop the socket and let the client find its own way back.
        sock = app.client.socket
        say("reconnect: dropping the link")
        sock.close()
        deadline = time.time() + 20
        while time.time() < deadline and not app.client.connected:
            time.sleep(0.2)
        say(f"reconnect: connected again={app.client.connected} seat={app.client.seat}")
        app.leave_game()

        # Tournament: host one, seat a bot, and get a match under way.
        app.host_tournament("SelfTest Cup", "round_robin", 1, 60, "csw", True, 2, 0)
        deadline = time.time() + 20
        while time.time() < deadline:
            if app.client and app.client.snapshot:
                break
            time.sleep(0.1)
        app.client.host_command(action="add_bot", level=1)
        app.client.host_command(action="start")
        deadline = time.time() + 30
        while time.time() < deadline:
            snapshot = app.client.snapshot if app.client else None
            if snapshot and snapshot.get("phase") == "playing" and snapshot.get("state"):
                ladder = snapshot.get("tournament") or {}
                say(f"tournament round={ladder.get('round')} format={ladder.get('format')} "
                    f"match_phase={snapshot.get('match_phase')}")
                break
            time.sleep(0.2)
        app.leave_game()

        ok = True
        say("PASS")
    except Exception as exc:
        say(f"FAIL {exc}")
        say(traceback.format_exc())
    finally:
        try:
            with open(_log_path(), "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
        except OSError:
            pass
    return 0 if ok else 1
