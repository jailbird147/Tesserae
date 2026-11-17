"""Package Tessera so it runs on macOS without a Mac having built it.

Produces dist/Tessera-MacOS.zip containing the Python sources, the data files,
and the universal (arm64 + x86_64) engine built by:

    python tools/build_engine.py --target macos

On the Mac the player unzips it and double-clicks Tessera.command. That creates
a .venv, installs pygame, ad-hoc signs the engine (Apple silicon refuses to run
unsigned binaries) and starts the game. Python 3.10+ must already be installed -
this is a source bundle, not a self-contained .app. For the .app, let
.github/workflows/macos.yml run PyInstaller on a real Mac.

    python tools/build_macos_bundle.py            personal build (all word lists)
    python tools/build_macos_bundle.py --store    free ENABLE list only
"""

import argparse
import os
import shutil
import struct
import sys
import zipfile

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(PROJ, "engine", "qengine")
STORE_WORDS = ("enable.txt", "enable.dawg")
STORE_DATA = ("strategy", "alphabets")
NAME = "Tessera-MacOS"

RUNNER = """#!/bin/sh
# Tessera for macOS. Double-click in Finder, or run:  sh run.sh
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "Tessera needs Python 3.10 or newer, and '$PY' was not found."
    echo "Get it from https://www.python.org/downloads/"
    echo "(or: brew install python@3.12, then run: PYTHON=python3.12 sh run.sh)"
    echo
    echo "Press return to close this window."
    read -r _
    exit 1
fi

version=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
case "$version" in
    3.1[0-9]) ;;
    *)  echo "Python $version found, but 3.10 or newer is needed."
        echo "Apple's own python3 is 3.9 - install a newer one from"
        echo "https://www.python.org/downloads/ (or: brew install python@3.12"
        echo "and then run: PYTHON=python3.12 sh run.sh)"
        read -r _
        exit 1 ;;
esac

if [ ! -d .venv ]; then
    echo "First run: creating a Python environment (one time only)..."
    "$PY" -m venv .venv
fi

echo "Checking pygame..."
./.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt

# Apple silicon refuses to execute unsigned code, and this binary was
# cross-compiled on a PC, so give it an ad-hoc signature.
if [ -f engine/qengine ]; then
    codesign --force --sign - engine/qengine >/dev/null 2>&1 || true
fi

exec ./.venv/bin/python run_tessera.py "$@"
"""

README = """# Tessera for macOS

A word game in the Scrabble family: play locally against 1-3 bots, or host a
game/tournament over the network.

## Running it

1. Install Python 3.10 or newer if you do not have it
   (https://www.python.org/downloads/ or `brew install python@3.12`).
2. Double-click **Tessera.command**.

   If macOS says the file cannot be opened because it is from an unidentified
   developer, either right-click it and choose **Open**, or run

       chmod +x Tessera.command

   once in Terminal, then double-click again.

   You can also run `sh run.sh` from Terminal - that needs no permissions fix.

The first run creates a `.venv` folder and installs pygame (a minute or so, it
needs an internet connection). Later runs start immediately.

## What this is

The game sources plus the Quackle engine compiled for macOS - a universal
binary that runs natively on Apple silicon and Intel Macs, macOS 11 or newer.
It is not a self-contained .app: it uses the Python you already have. A packaged
.app/.dmg is built by GitHub Actions on a real Mac (see the main README).

## Notes

* Settings, including imported word lists, live in `settings.json` next to this
  file.
* `data/` holds the dictionaries and Quackle's strategy files. {word_lists}
* Quackle is GPL v3: see LICENSE and THIRD-PARTY-LICENCES.md.
"""


def check_engine() -> None:
    if not os.path.exists(ENGINE):
        raise SystemExit("engine/qengine is missing - run: "
                         "python tools/build_engine.py --target macos")
    with open(ENGINE, "rb") as fh:
        magic = fh.read(4)
    if magic == b"\xcf\xfa\xed\xfe":
        print("engine: single-architecture Mach-O (fine, but not universal)")
    elif magic == b"\xca\xfe\xba\xbe":
        print("engine: universal Mach-O")
    else:
        raise SystemExit("engine/qengine is not a macOS binary - rebuild it with "
                         "--target macos")


def stage(store: bool) -> str:
    staging = os.path.join(PROJ, "build", "macos-bundle", NAME)
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    shutil.copytree(os.path.join(PROJ, "tessera"), os.path.join(staging, "tessera"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(os.path.join(PROJ, "assets"), os.path.join(staging, "assets"))
    for name in ("run_tessera.py", "requirements.txt", "LICENSE", "THIRD-PARTY-LICENCES.md"):
        shutil.copy2(os.path.join(PROJ, name), os.path.join(staging, name))

    os.makedirs(os.path.join(staging, "engine"), exist_ok=True)
    shutil.copy2(ENGINE, os.path.join(staging, "engine", "qengine"))

    data_src = os.path.join(PROJ, "data")
    data_dst = os.path.join(staging, "data")
    os.makedirs(data_dst, exist_ok=True)
    for name in os.listdir(data_src):
        source = os.path.join(data_src, name)
        if os.path.isdir(source):
            if store and name not in STORE_DATA:
                continue
            shutil.copytree(source, os.path.join(data_dst, name))
        elif store and name not in STORE_WORDS:
            continue
        else:
            shutil.copy2(source, os.path.join(data_dst, name))

    for name in ("run.sh", "Tessera.command"):
        path = os.path.join(staging, name)
        with open(path, "w", newline="\n") as fh:
            fh.write(RUNNER)
    word_lists = ("Only the free ENABLE word list is included in this build."
                  if store else
                  "The Collins CSW24 and SOWPODS lists are here for personal play "
                  "and are not redistributable - do not share this folder with "
                  "anyone else.")
    with open(os.path.join(staging, "README-macOS.md"), "w", newline="\n") as fh:
        fh.write(README.format(word_lists=word_lists))
    return staging


def zip_tree(staging: str, out: str) -> None:
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(staging):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(root, name)
                rel = os.path.relpath(path, os.path.dirname(staging)).replace(os.sep, "/")
                info = zipfile.ZipInfo.from_file(path, rel)
                executable = name in ("run.sh", "Tessera.command") or name == "qengine"
                mode = 0o755 if executable else 0o644
                info.external_attr = (0o100000 | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(path, "rb") as src, zf.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Package Tessera for macOS.")
    parser.add_argument("--store", action="store_true",
                        help="ship the free ENABLE word list only")
    parser.add_argument("--out", default=os.path.join(PROJ, "dist", "Tessera-MacOS.zip"))
    args = parser.parse_args()

    if not sys.platform.startswith("win") and not sys.platform == "darwin":
        print("note: this bundle is meant to be built on Windows or macOS")
    check_engine()
    staging = stage(args.store)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    zip_tree(staging, args.out)
    size = os.path.getsize(args.out) / (1024 * 1024)
    print(f"built {args.out} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
