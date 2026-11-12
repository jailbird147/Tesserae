import os
import subprocess
import sys
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(PROJ, "engine", "qengine.exe")

for dawg in ("data/csw24.dawg", "data/sowpods.dawg"):
    proc = subprocess.Popen([EXE], cwd=PROJ, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, bufsize=1)
    proc.stdin.write(f"INIT data=data dawg={dawg} lexicon=csw\n")
    proc.stdin.flush()
    line = proc.stdout.readline().strip()
    print(dawg, "->", line)
    if line.startswith("OK"):
        proc.stdin.write("MOVES board=" + "." * 225 + " rack=AEIRST? bag=" + "AEIOULNSTR" * 8 +
                         " my=0 opp=0 level=1 top=2 secs=1\n")
        proc.stdin.flush()
        start = time.time()
        while time.time() - start < 10:
            out = proc.stdout.readline().strip()
            print("   ", out)
            if out.startswith("END") or out.startswith("ERR"):
                break
    proc.stdin.write("QUIT\n")
    proc.stdin.flush()
    try:
        proc.wait(timeout=2)
    except Exception:
        proc.kill()
