"""Package Tessera as an MSIX for the Microsoft Store.

    F:\\Python312\\python.exe tools\\build_msix.py

What it does:
  1. builds (or reuses) the Store build at dist\\store\\Tessera
  2. draws the Store logos into dist\\msix\\layout\\Assets
  3. writes AppxManifest.xml
  4. packs dist\\Tessera.msix with makeappx

The Store re-signs the package after certification, so no certificate is needed
for submission. To test locally, register the layout folder (Developer Mode):

    Add-AppxPackage -Register dist\\msix\\layout\\AppxManifest.xml

Identity: the package Name and Publisher must match what Partner Center gives
you when you reserve the name. Set them with environment variables:

    set TESSERA_STORE_NAME=12345Smith.Tessera
    set TESSERA_STORE_PUBLISHER=CN=0A1B2C3D-....

Until then the placeholders below are used, which are fine for side-loading.

makeappx.exe is looked for in F:\\toolchains\\msix, then on PATH, then in the
Windows SDK. Without it the layout folder is still produced.
"""

import os
import shutil
import subprocess
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)

BUILD = os.path.join(PROJ, "dist", "store", "Tessera")
LAYOUT = os.path.join(PROJ, "dist", "msix", "layout")
MSIX = os.path.join(PROJ, "dist", "Tessera.msix")

NAME = os.environ.get("TESSERA_STORE_NAME", "Tessera.Tessera")
PUBLISHER = os.environ.get("TESSERA_STORE_PUBLISHER", "CN=Tessera")
PUBLISHER_DISPLAY = os.environ.get("TESSERA_STORE_PUBLISHER_NAME", "Tessera")
VERSION = os.environ.get("TESSERA_STORE_VERSION", "1.0.0.0")

MAKEFILES = [
    os.path.join(r"F:\toolchains\msix", "makeappx.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Windows Kits", "10", "bin", "10.0.22621.0", "x64", "makeappx.exe"),
]


def find_makeappx() -> str | None:
    for path in MAKEFILES:
        if path and os.path.exists(path):
            return path
    return shutil.which("makeappx")


def draw_assets() -> None:
    """Store logos drawn with pygame: a cream tile on the ink background."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from tessera.ui import theme

    pygame.init()
    pygame.display.set_mode((1, 1))
    assets = os.path.join(LAYOUT, "Assets")
    os.makedirs(assets, exist_ok=True)

    def logo(size: int, wide: bool = False):
        surface = pygame.Surface((size, size))
        surface.fill(theme.BG_DARK)
        inner = int(size * 0.72)
        x = (size - inner) // 2
        if wide:
            surface = pygame.Surface((size, size))
        rect = pygame.Rect(x, x, inner, inner)
        tile = theme.draw_tile(surface, rect, "T", 1, value_color=theme.ACCENT_DARK)
        return surface if tile is None else surface

    for filename, size in (
        ("StoreLogo.png", 50),
        ("Square44x44Logo.png", 44),
        ("Square150x150Logo.png", 150),
        ("Square310x310Logo.png", 310),
    ):
        pygame.image.save(logo(size), os.path.join(assets, filename))

    wide = pygame.Surface((310, 150))
    wide.fill(theme.BG_DARK)
    tile = pygame.Rect(75, 30, 90, 90)
    theme.draw_tile(wide, tile, "T", 1, value_color=theme.ACCENT_DARK)
    pygame.image.save(wide, os.path.join(assets, "Wide310x150Logo.png"))
    pygame.quit()


MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap10="http://schemas.microsoft.com/appx/manifest/uap/windows10/10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap10 rescap">

  <Identity Name="{name}" Publisher="{publisher}" Version="{version}"
            ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>Tesserae</DisplayName>
    <PublisherDisplayName>{publisher_display}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <Description>A word game for Windows, played against Quackle bots or up to sixteen people online.</Description>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0"
                        MaxVersionTested="10.0.22621.0" />
  </Dependencies>

  <Resources>
    <Resource Language="en-GB" />
  </Resources>

  <Applications>
    <Application Id="Tessera" Executable="Tessera.exe"
                 EntryPoint="Windows.FullTrustApplication"
                 uap10:TrustLevel="mediumIL" uap10:RuntimeBehavior="packagedClassicApp">
      <uap:VisualElements DisplayName="Tesserae"
                          Description="A word game for Windows, played against Quackle bots or up to sixteen people online."
                          BackgroundColor="#0E3A3C"
                          Square150x150Logo="Assets\\Square150x150Logo.png"
                          Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png"
                         Square310x310Logo="Assets\\Square310x310Logo.png" />
      </uap:VisualElements>
    </Application>
  </Applications>

  <Capabilities>
    <Capability Name="internetClient" />
    <Capability Name="privateNetworkClientServer" />
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def build_layout() -> None:
    if not os.path.exists(os.path.join(BUILD, "Tessera.exe")):
        print("No Store build found. Building it now...")
        result = subprocess.run([sys.executable, os.path.join(PROJ, "tools", "build_exe.py"), "--store"])
        if result.returncode != 0:
            raise SystemExit("Store build failed.")
    if not os.path.exists(os.path.join(BUILD, "Tessera.exe")):
        raise SystemExit(f"Store build missing: {BUILD}")

    shutil.rmtree(os.path.join(PROJ, "dist", "msix"), ignore_errors=True)
    shutil.copytree(BUILD, LAYOUT)
    draw_assets()
    manifest = MANIFEST.format(name=NAME, publisher=PUBLISHER, version=VERSION,
                               publisher_display=PUBLISHER_DISPLAY)
    with open(os.path.join(LAYOUT, "AppxManifest.xml"), "w", encoding="utf-8") as handle:
        handle.write(manifest)
    print("layout ready:", LAYOUT)


def pack() -> int:
    makeappx = find_makeappx()
    if not makeappx:
        print("makeappx.exe not found — the layout folder is ready, pack it on a machine "
              "with the Windows SDK.")
        print("Layout:", LAYOUT)
        return 0
    result = subprocess.run([makeappx, "pack", "/d", LAYOUT, "/p", MSIX, "/o"], capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip())
        return result.returncode
    size = os.path.getsize(MSIX) / (1024 * 1024)
    print(f"packed {MSIX} ({size:.1f} MB)")
    return 0


def main() -> int:
    build_layout()
    return pack()


if __name__ == "__main__":
    sys.exit(main())
