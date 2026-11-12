import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.session import Session

session = Session(turn_seconds=60, allow_blank_recycle=True, seats=4)
for index in range(4):
    session.add_bot(index, 1 + index % 3)
    session.seat_list[index].name = f"Bot{index + 1}"
session.start()

start = time.time()
while time.time() - start < 150:
    snap = session.snapshot(None)
    if snap["phase"] != "playing":
        break
    time.sleep(0.2)

snap = session.snapshot(None)
state = snap["state"]
print("phase", snap["phase"], "turn", state["turn"], "bag", state["bag"])
for player in state["players"]:
    print(f"  {player['name']:<8} {player['score']:>4}  tiles={player['tiles_left']}")
print("result:", state["result"])
print("history:", len(state["history"]))
session.close()
