"""Build the Quackle bridge executable (qengine.exe).

Compiles libquackle sources one at a time (incremental) and links them with
qengine.cpp. Requires MinGW-w64 g++ at F:\\toolchains\\mingw64\\bin\\g++.exe.
"""

import os
import subprocess
import sys
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJ, "engine", "quackle")
OBJ = os.path.join(PROJ, "engine", "obj")
OUT = os.path.join(PROJ, "engine", "qengine.exe")
CXX = r"F:\toolchains\mingw64\bin\g++.exe"

EXCLUDE = {"loaddawg.cpp", "loadgaddag.cpp", "makedawg.cpp", "quackletest.cpp"}
EXTRA_SOURCES = [os.path.join("test", "trademarkedboards.cpp")]

os.makedirs(OBJ, exist_ok=True)

sources = sorted(f for f in os.listdir(SRC) if f.endswith(".cpp") and f not in EXCLUDE)
sources.extend(EXTRA_SOURCES)
assert "qengine.cpp" in sources

FLAGS = [CXX, "-O2", "-std=c++17", "-w", "-pthread", "-DNDEBUG", "-I" + SRC, "-I" + os.path.join(SRC, "test"),
         "-D_WIN32_WINNT=0x0A00", "-DWINVER=0x0A00"]

objects = []
failures = []
for name in sources:
    obj = os.path.join(OBJ, name.replace(os.sep, "_")[:-4] + ".o")
    objects.append(obj)
    src = os.path.join(SRC, name)
    if os.path.exists(obj) and os.path.getmtime(obj) >= os.path.getmtime(src):
        continue
    started = time.time()
    r = subprocess.run(FLAGS + ["-c", src, "-o", obj], cwd=SRC, capture_output=True, text=True)
    status = "ok" if r.returncode == 0 else "FAIL"
    print(f"[{status}] {name} ({time.time() - started:.1f}s)", flush=True)
    if r.returncode != 0:
        failures.append((name, r.stderr))
        print(r.stderr[-4000:], flush=True)

if failures:
    print(f"{len(failures)} file(s) failed to compile", flush=True)
    sys.exit(1)

print("linking...", flush=True)
r = subprocess.run(FLAGS + objects + ["-o", OUT], cwd=SRC, capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr[-8000:], flush=True)
    sys.exit(r.returncode)
print("built", OUT, flush=True)

# The game ships the MinGW runtime next to the exe rather than relying on PATH.
import shutil
bin_dir = os.path.dirname(CXX)
for dll in ("libstdc++-6.dll", "libgcc_s_seh-1.dll", "libwinpthread-1.dll"):
    source = os.path.join(bin_dir, dll)
    if os.path.exists(source):
        shutil.copy2(source, os.path.join(os.path.dirname(OUT), dll))
print("runtime dlls copied", flush=True)
