"""Build a standalone Windows build (folder distribution) with PyInstaller.

    F:\\Python312\\python.exe tools\\build_exe.py           personal build
    F:\\Python312\\python.exe tools\\build_exe.py --store    build for the Store

The Store build ships the free ENABLE word list only. The Collins CSW24 and
SOWPODS lists are copyright and cannot be redistributed in a public Store app,
so they are left out; players who own them can import them in Settings.
"""

import os
import shutil
import subprocess
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = r"F:\Python312\python.exe"
STORE_WORDS = ("enable.txt", "enable.dawg")


def _stage_store_data() -> str:
    """Copy the data folder without the licensed word lists."""
    staging = os.path.join(PROJ, "build", "store_data")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    for name in STORE_WORDS:
        shutil.copy2(os.path.join(PROJ, "data", name), os.path.join(staging, name))
    for folder in ("strategy", "alphabets"):
        shutil.copytree(os.path.join(PROJ, "data", folder), os.path.join(staging, folder))
    for name in ("LICENSE", "THIRD-PARTY-LICENCES.md"):
        shutil.copy2(os.path.join(PROJ, name), os.path.join(staging, name))
    return staging


def main() -> int:
    store = "--store" in sys.argv
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("installing pyinstaller...")
        subprocess.run([PY, "-m", "pip", "install", "pyinstaller"], check=True)

    data_dir = _stage_store_data() if store else os.path.join(PROJ, "data")
    dist = os.path.join(PROJ, "dist", "store") if store else os.path.join(PROJ, "dist")

    args = [
        PY, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",
        "--name", "Tessera",
        "--icon", os.path.join(PROJ, "assets", "app.ico"),
        "--distpath", dist,
        "--workpath", os.path.join(PROJ, "build"),
        "--specpath", os.path.join(PROJ, "build"),
        "--add-data", data_dir + ";data",
        "--add-data", os.path.join(PROJ, "assets") + ";assets",
        "--add-data", os.path.join(PROJ, "engine", "qengine.exe") + ";engine",
        "--add-data", os.path.join(PROJ, "engine", "libgcc_s_seh-1.dll") + ";engine",
        "--add-data", os.path.join(PROJ, "engine", "libstdc++-6.dll") + ";engine",
        "--add-data", os.path.join(PROJ, "engine", "libwinpthread-1.dll") + ";engine",
        "--exclude-module", "tkinter",
        "--exclude-module", "unittest",
        os.path.join(PROJ, "run_tessera.py"),
    ]
    print(" ".join(f'"{a}"' if " " in a else a for a in args))
    result = subprocess.run(args, cwd=PROJ)
    if result.returncode == 0:
        print("built", os.path.join(dist, "Tessera", "Tessera.exe"))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
