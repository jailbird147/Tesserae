import os
import subprocess
import sys
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(PROJ, "engine", "qengine.exe")
DATA = os.path.join(PROJ, "data")


def send(proc, line):
    proc.stdin.write(line + "\n")
    proc.stdin.flush()


def read_until_end(proc, timeout=60):
    lines = []
    start = time.time()
    while time.time() - start < timeout:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.rstrip()
        lines.append(line)
        if line.startswith("END") or line.startswith("ERR") or line.startswith("OK") or line.startswith("PONG"):
            break
    return lines


proc = subprocess.Popen([EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        text=True, bufsize=1, cwd=PROJ)

send(proc, "PING")
print(read_until_end(proc))

send(proc, "INIT data=data dawg=data/csw24.dawg lexicon=csw")
print(read_until_end(proc, 120))

empty = "." * 225
start = time.time()
send(proc, f"MOVES board={empty} rack=AEIRST? bag={'A' * 92} level=1 top=10 my=0 opp=0")
print("\n".join(read_until_end(proc, 120)))
print("level1 time %.2fs" % (time.time() - start))

start = time.time()
send(proc, f"MOVES board={empty} rack=AEIRST? bag={'A' * 92} level=3 top=5 my=0 opp=0 secs=3")
print("\n".join(read_until_end(proc, 120)))
print("level3 time %.2fs" % (time.time() - start))

start = time.time()
send(proc, f"MOVES board={empty} rack=AEIRST? bag={'A' * 92} level=5 top=3 my=0 opp=0 secs=5")
print("\n".join(read_until_end(proc, 120)))
print("level5 time %.2fs" % (time.time() - start))

send(proc, "QUIT")
print(proc.stdout.read())
proc.wait()
