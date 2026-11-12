import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.session import Session

session = Session(turn_seconds=180, allow_blank_recycle=True, seats=2)
for index, level in enumerate((3, 4)):
    session.add_bot(index, level)
    session.seat_list[index].name = f"Bot{index + 1}L{level}"
session.start()

start = time.time()
while time.time() - start < 120:
    snap = session.snapshot(None)
    if snap["phase"] != "playing":
        break
    time.sleep(0.2)

snap = session.snapshot(None)
for player in snap["state"]["players"]:
    print(player["name"], player["score"], player["tiles_left"])
print("turns", snap["state"]["turn"], "result", snap["state"]["result"])
for record in snap["state"]["history"]:
    print(record["turn"], record["name"], record["kind"], record["detail"], record["score"])
print("last_error", session.last_error)
session.close()
