"""Check the EVAL command scores a given move."""

import os
import subprocess
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(PROJ, "engine", "qengine.exe")


def ask(proc, line, terminators=("SCORE", "END", "ERR", "OK")):
    proc.stdin.write(line + "\n")
    proc.stdin.flush()
    out = []
    while True:
        reply = proc.stdout.readline().strip()
        if not reply:
            break
        out.append(reply)
        if reply.startswith(terminators):
            break
    return out


proc = subprocess.Popen([EXE], cwd=PROJ, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        text=True, bufsize=1)
print(ask(proc, "INIT data=data dawg=data/csw24.dawg lexicon=csw"))
board = "." * 225
print(ask(proc, f"EVAL board={board} rack=AEIRST? bag={'AEIOULNSTR' * 8} my=0 opp=0 "
                "row=7 col=1 horiz=1 tiles=ARTIEST"))

# Now a mid-board move: build a board with a vertical word and score a cross-play.
cells = ["."] * 225
for row, letter in zip(range(5, 12), "QUARTZY"):
    cells[row * 15 + 7] = letter
grid = "".join(cells)
print(ask(proc, f"EVAL board={grid} rack=AEIRST? bag={'AEIOULNSTR' * 8} my=0 opp=0 "
                "row=10 col=7 horiz=0 tiles=.ARTIEST"))
print(ask(proc, f"EVAL board={grid} rack=AEIRST? bag={'AEIOULNSTR' * 8} my=0 opp=0 "
                "row=5 col=7 horiz=1 tiles=QUaRTZY"))
proc.stdin.write("QUIT\n")
proc.stdin.flush()
