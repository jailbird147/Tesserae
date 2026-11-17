"""Build the Quackle bridge executable (engine/qengine).

Compiles libquackle sources one at a time (incremental) and links them with
qengine.cpp.

    python tools/build_engine.py                  native build for this machine
    python tools/build_engine.py --target macos   macOS build

Native on Windows uses MinGW-w64 g++ at F:\\toolchains\\mingw64\\bin\\g++.exe and
writes engine/qengine.exe plus the MinGW runtime DLLs.

Native on macOS uses clang++ from the Xcode Command Line Tools and writes
engine/qengine.

`--target macos` from a Windows or Linux host cross-compiles with zig
(F:\\toolchains\\zig), which ships its own macOS libSystem libc/libc++ stubs, so
no Mac and no Apple SDK are needed. It emits a universal binary: one arm64 and
one x86_64 slice merged into engine/qengine.

Set QUACKLE_CXX to use a different native compiler, ZIG to override the zig
executable.
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
import time

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJ, "engine", "quackle")
ENGINE_DIR = os.path.join(PROJ, "engine")
MINGW_CXX = r"F:\toolchains\mingw64\bin\g++.exe"
ZIG_FALLBACK = r"F:\toolchains\zig\zig.exe"

EXCLUDE = {"loaddawg.cpp", "loadgaddag.cpp", "makedawg.cpp", "quackletest.cpp"}
EXTRA_SOURCES = [os.path.join("test", "trademarkedboards.cpp")]
MACOS_DEPLOYMENT = "11.0"


def source_list() -> list[str]:
    names = sorted(f for f in os.listdir(SRC) if f.endswith(".cpp") and f not in EXCLUDE)
    names.extend(EXTRA_SOURCES)
    assert "qengine.cpp" in names, "qengine.cpp must be part of the engine bridge"
    return names


def compile_and_link(compiler: list[str], flags: list[str], obj_dir: str,
                     out: str, label: str) -> int:
    """Compile each translation unit that changed, then link. Returns exit code."""
    os.makedirs(obj_dir, exist_ok=True)
    objects, failures = [], []
    for name in source_list():
        obj = os.path.join(obj_dir, name.replace(os.sep, "_")[:-4] + ".o")
        objects.append(obj)
        src = os.path.join(SRC, name)
        if os.path.exists(obj) and os.path.getmtime(obj) >= os.path.getmtime(src):
            continue
        started = time.time()
        r = subprocess.run(compiler + flags + ["-c", src, "-o", obj],
                           cwd=SRC, capture_output=True, text=True)
        status = "ok" if r.returncode == 0 else "FAIL"
        print(f"[{label} {status}] {name} ({time.time() - started:.1f}s)", flush=True)
        if r.returncode != 0:
            failures.append(name)
            print(r.stderr[-4000:], flush=True)
    if failures:
        print(f"{len(failures)} file(s) failed to compile: {', '.join(failures)}", flush=True)
        return 1

    print(f"[{label}] linking {out}", flush=True)
    r = subprocess.run(compiler + flags + objects + ["-o", out], cwd=SRC,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-8000:], flush=True)
        return r.returncode
    return 0


# ------------------------------------------------------------------- native
def build_native() -> int:
    cxx = os.environ.get("QUACKLE_CXX")
    if not cxx:
        cxx = MINGW_CXX if IS_WINDOWS else (shutil.which("clang++") or "clang++")
    out = os.path.join(ENGINE_DIR, "qengine.exe" if IS_WINDOWS else "qengine")
    # Separate object trees per platform: MinGW, clang and zig objects are not
    # interchangeable, and mixing them would silently skip a rebuild.
    obj_dir = os.path.join(ENGINE_DIR, "obj") if IS_WINDOWS else os.path.join(ENGINE_DIR, "obj", "macos")
    flags = ["-O2", "-std=c++17", "-w", "-pthread", "-DNDEBUG",
             "-I" + SRC, "-I" + os.path.join(SRC, "test")]
    if IS_WINDOWS:
        flags += ["-D_WIN32_WINNT=0x0A00", "-DWINVER=0x0A00"]

    code = compile_and_link([cxx], flags, obj_dir, out, "native")
    if code or not IS_WINDOWS:
        return code

    # The game ships the MinGW runtime next to the exe rather than relying on PATH.
    bin_dir = os.path.dirname(cxx)
    for dll in ("libstdc++-6.dll", "libgcc_s_seh-1.dll", "libwinpthread-1.dll"):
        source = os.path.join(bin_dir, dll)
        if os.path.exists(source):
            shutil.copy2(source, os.path.join(ENGINE_DIR, dll))
    print("runtime dlls copied", flush=True)
    return 0


# ------------------------------------------------------ cross-build (zig)
def zig() -> str:
    path = os.environ.get("ZIG") or shutil.which("zig") or ZIG_FALLBACK
    if not os.path.exists(path) and not shutil.which(path):
        raise SystemExit("zig not found; set ZIG to the zig executable")
    return path


def macho_header(path: str) -> tuple[int, int]:
    """cputype, cpusubtype of a 64-bit little-endian Mach-O file."""
    with open(path, "rb") as fh:
        head = fh.read(16)
    magic, cputype, cpusubtype, _filetype = struct.unpack("<IIII", head)
    if magic != 0xFEEDFACF:
        raise SystemExit(f"{path} is not a 64-bit Mach-O file")
    return cputype, cpusubtype


def write_fat(slices: list[str], out: str, align_bits: int = 14) -> None:
    """Merge Mach-O slices into one universal binary (FAT_MAGIC, big-endian)."""
    align = 1 << align_bits
    entries, payloads = [], []
    end = 8 + 20 * len(slices)
    for path in slices:
        cputype, cpusubtype = macho_header(path)
        with open(path, "rb") as fh:
            data = fh.read()
        offset = (end + align - 1) & ~(align - 1)
        entries.append((cputype, cpusubtype, offset, len(data), align_bits))
        payloads.append((offset, data))
        end = offset + len(data)

    buf = bytearray(end)
    struct.pack_into(">II", buf, 0, 0xCAFEBABE, len(slices))
    for i, (cputype, cpusubtype, offset, size, bits) in enumerate(entries):
        struct.pack_into(">IIIII", buf, 8 + 20 * i,
                         cputype, cpusubtype & 0xFFFFFFFF, offset, size, bits)
    for offset, data in payloads:
        buf[offset:offset + len(data)] = data
    with open(out, "wb") as fh:
        fh.write(buf)
    print("universal binary:", out,
          [(hex(e[0]), e[3]) for e in entries], flush=True)


def build_cross_macos() -> int:
    compiler = [zig(), "c++"]
    base = ["-O2", "-std=c++17", "-w", "-DNDEBUG", "-I" + SRC, "-I" + os.path.join(SRC, "test")]
    slices = []
    for target, label in ((f"aarch64-macos.{MACOS_DEPLOYMENT}", "macos-arm64"),
                          (f"x86_64-macos.{MACOS_DEPLOYMENT}", "macos-x86_64")):
        out = os.path.join(ENGINE_DIR, "obj", label + ".slice")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        code = compile_and_link(compiler, ["-target", target] + base,
                                os.path.join(ENGINE_DIR, "obj", label), out, label)
        if code:
            return code
        slices.append(out)

    merged = os.path.join(ENGINE_DIR, "qengine")
    write_fat(slices, merged)
    for slice_path in slices:
        os.remove(slice_path)
    print("built", merged, flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Quackle bridge executable.")
    parser.add_argument("--target", choices=("auto", "windows", "macos"), default="auto",
                        help="auto = this machine's platform; macos from Windows/Linux "
                             "cross-compiles with zig into a universal binary")
    args = parser.parse_args()

    if args.target == "macos" and not IS_MAC:
        return build_cross_macos()
    return build_native()


if __name__ == "__main__":
    sys.exit(main())
