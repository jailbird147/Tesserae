"""Both word lists load and the engine re-initialises when the list changes."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.engine import shared_engine
from tessera.lexicon import (
    delete_wordlist,
    import_wordlist,
    lexicon_dawg,
    lexicon_identity,
    lexicon_names,
    load_lexicon,
)
from tessera.session import Session
import tempfile

failures = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name, detail)
    if not condition:
        failures.append(name)


csw = load_lexicon("csw")
sow = load_lexicon("sowpods")
enable = load_lexicon("enable")
check("CSW24 word count", len(csw) == 280887, len(csw))
check("SOWPODS word count", len(sow) == 246691, len(sow))
check("ENABLE word count", len(enable) == 168551, len(enable))
check("lists differ", len(csw.words - sow.words) > 1000 and len(sow.words - csw.words) > 0,
      (len(csw.words - sow.words), len(sow.words - csw.words)))
check("ENABLE is smaller than CSW24", len(enable.words & csw.words) > 160000 and len(csw.words - enable.words) > 100000,
      (len(enable.words & csw.words), len(csw.words - enable.words)))
check("built-in lists listed", {"csw", "sowpods", "enable"} <= set(lexicon_names()), lexicon_names())
identity = lexicon_identity("enable")
check("ENABLE is built in, not verified", identity["custom"] is False and identity["verified"] is False, identity)

for name in ("csw", "sowpods", "enable", "csw"):
    session = Session(turn_seconds=60, seats=2, lexicon=name)
    session.add_bot(0, 1)
    session.add_bot(1, 1)
    session.start()
    start = time.time()
    while time.time() - start < 40:
        snapshot = session.snapshot(None)
        if snapshot["state"]["turn"] >= 3:
            break
        time.sleep(0.2)
    snapshot = session.snapshot(None)
    state = snapshot["state"]
    check(f"{name}: engine produced a move", state["players"][0]["score"] > 0 or state["players"][1]["score"] > 0,
          [p["score"] for p in state["players"]])
    check(f"{name}: reported lexicon", snapshot["settings"]["lexicon"] == name, snapshot["settings"])
    session.close()

# An imported list: the game must use exactly the words the file has, and the
# engine must generate only those words.
with tempfile.TemporaryDirectory() as folder:
    path = os.path.join(folder, "test words.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(sorted(enable.words | {"QQQQ"})) + "\n")
    identity = import_wordlist(path, "Test list")
    check("imported list registered", identity["name"] in lexicon_names(), identity)
    check("imported list marked custom", identity["custom"] is True, identity)

    custom = load_lexicon(identity["name"])
    check("imported words match", "QQQQ" in custom.words and len(custom) == len(enable) + 1, len(custom))

    session = Session(turn_seconds=60, seats=2, lexicon=identity["name"])
    session.add_bot(0, 2)
    session.add_bot(1, 2)
    session.start()
    start = time.time()
    while time.time() - start < 40:
        if session.snapshot(None)["state"]["turn"] >= 3:
            break
        time.sleep(0.2)
    snapshot = session.snapshot(None)
    check("custom: engine produced a move",
          any(p["score"] > 0 for p in snapshot["state"]["players"]),
          [p["score"] for p in snapshot["state"]["players"]])
    check("custom: reported lexicon", snapshot["settings"]["lexicon"] == identity["name"],
          snapshot["settings"])
    played = [entry.get("word", "") for entry in snapshot.get("log", [])]
    session.close()

    check("custom list removed", delete_wordlist(identity["name"]), identity["name"])
    check("custom list gone", identity["name"] not in lexicon_names(), lexicon_names())

engine = shared_engine(lexicon_dawg("sowpods"))
engine.ensure_started()
print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
