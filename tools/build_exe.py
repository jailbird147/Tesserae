"""Build a standalone app with PyInstaller.

    Windows:  F:\\Python312\\python.exe tools\\build_exe.py [--store]
              -> dist\\Tessera\\Tessera.exe   (folder build; build_msix.py uses it)

    macOS:    python3 tools/build_exe.py [--store] [--dmg]
              -> dist/Tessera.app           (and dist/Tessera.dmg with --dmg)

PyInstaller is not a cross-compiler: a Windows build has to be made on Windows
and a macOS build on macOS. .github/workflows/macos.yml does the macOS one on
a GitHub-hosted runner.

The Store build ships the free ENABLE word list only. The Collins CSW24 and
SOWPODS lists are copyright and cannot be redistributed in a public Store app,
so they are left out; players who own them can import them in Settings.
"""

import argparse
import os
import shutil
import subprocess
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"
SEP = os.pathsep  # PyInstaller --add-data separator: ';' on Windows, ':' on macOS
STORE_WORDS = ("enable.txt", "enable.dawg")
BUNDLE_ID = "com.jailbird.tessera"


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


def _data_arg(source: str, dest: str) -> list[str]:
    return ["--add-data", f"{source}{SEP}{dest}"]


# ------------------------------------------------------------------ macOS bits
def ensure_icns() -> str:
    """Build build/Tessera.icns from assets/icon.png using sips + iconutil."""
    icns = os.path.join(PROJ, "build", "Tessera.icns")
    source = os.path.join(PROJ, "assets", "icon-1024.png")
    if not os.path.exists(source):
        source = os.path.join(PROJ, "assets", "icon.png")
    if os.path.exists(icns) and os.path.getmtime(icns) >= os.path.getmtime(source):
        return icns

    iconset = os.path.join(PROJ, "build", "Tessera.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset, exist_ok=True)
    for size, name in ((16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
                       (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
                       (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
                       (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
                       (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png")):
        subprocess.run(["sips", "-z", str(size), str(size), source, "--out",
                        os.path.join(iconset, name)],
                       check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True, capture_output=True)
    print("icon:", icns)
    return icns


def _chmod_engine(app: str) -> None:
    """PyInstaller does not always keep the +x bit on collected data files."""
    for root, _dirs, files in os.walk(app):
        for name in files:
            if name in ("qengine", "qengine.exe"):
                path = os.path.join(root, name)
                os.chmod(path, 0o755)
                print("engine:", path)


def sign(app: str, identity: str | None) -> int:
    """Sign the bundle. Ad-hoc ('-') is enough to run it on the build machine."""
    ident = identity or os.environ.get("CODESIGN_IDENTITY")
    if ident:
        cmd = ["codesign", "--force", "--deep", "--timestamp", "--options", "runtime",
               "--sign", ident, app]
        print("signing with", ident)
    else:
        cmd = ["codesign", "--force", "--deep", "--sign", "-", app]
        print("signing ad-hoc (not distributable outside this machine)")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        subprocess.run(["codesign", "--verify", "--deep", "--strict", app])
    return result.returncode


def make_dmg(app: str) -> str:
    dmg = os.path.join(PROJ, "dist", "Tessera.dmg")
    if os.path.exists(dmg):
        os.remove(dmg)
    subprocess.run(["hdiutil", "create", "-volname", "Tessera", "-srcfolder", app,
                    "-ov", "-format", "UDZO", dmg], check=True, capture_output=True)
    print("built", dmg)
    return dmg


def notarize(path: str) -> None:
    """Submit for notarization when Apple credentials are in the environment."""
    apple_id = os.environ.get("APPLE_ID")
    team_id = os.environ.get("APPLE_TEAM_ID")
    password = os.environ.get("APPLE_APP_PASSWORD")
    if not (apple_id and team_id and password):
        print("notarization: skipped (set APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD)")
        return
    print("notarizing", path, "(this can take a while)")
    subprocess.run(["xcrun", "notarytool", "submit", path, "--apple-id", apple_id,
                    "--team-id", team_id, "--password", password, "--wait"], check=True)
    subprocess.run(["xcrun", "stapler", "staple", path], check=True)


# ----------------------------------------------------------------------- build
def main() -> int:
    parser = argparse.ArgumentParser(description="Build Tessera with PyInstaller.")
    parser.add_argument("--store", action="store_true",
                        help="ship the free ENABLE word list only (public release)")
    parser.add_argument("--dmg", action="store_true", help="macOS: also write dist/Tessera.dmg")
    parser.add_argument("--sign", default=None, help="macOS: codesign identity")
    parser.add_argument("--no-sign", action="store_true", help="macOS: skip codesigning")
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("installing pyinstaller...")
        subprocess.run([PY, "-m", "pip", "install", "pyinstaller"], check=True)

    data_dir = _stage_store_data() if args.store else os.path.join(PROJ, "data")
    dist = os.path.join(PROJ, "dist", "store") if args.store else os.path.join(PROJ, "dist")
    engine = os.path.join(PROJ, "engine", "qengine.exe" if IS_WINDOWS else "qengine")

    cmd = [
        PY, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",
        "--name", "Tessera",
        "--distpath", dist,
        "--workpath", os.path.join(PROJ, "build"),
        "--specpath", os.path.join(PROJ, "build"),
    ]
    cmd += _data_arg(data_dir, "data")
    cmd += _data_arg(os.path.join(PROJ, "assets"), "assets")
    cmd += _data_arg(engine, "engine")
    if IS_WINDOWS:
        cmd += ["--icon", os.path.join(PROJ, "assets", "app.ico")]
        for dll in ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"):
            cmd += _data_arg(os.path.join(PROJ, "engine", dll), "engine")
    elif IS_MAC:
        cmd += ["--icon", ensure_icns(), "--osx-bundle-identifier", BUNDLE_ID]
    cmd += ["--exclude-module", "tkinter", "--exclude-module", "unittest"]
    cmd.append(os.path.join(PROJ, "run_tessera.py"))

    print(" ".join(f'"{a}"' if " " in a else a for a in cmd))
    result = subprocess.run(cmd, cwd=PROJ)
    if result.returncode != 0:
        return result.returncode

    if IS_MAC:
        app = os.path.join(dist, "Tessera.app")
        if not os.path.isdir(app):
            print("expected", app, "but it is missing")
            return 1
        _chmod_engine(app)
        if not args.no_sign and sign(app, args.sign) != 0:
            return 1
        notarize(app)
        if args.dmg:
            make_dmg(app)
        print("built", app)
    else:
        print("built", os.path.join(dist, "Tessera", "Tessera.exe"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
