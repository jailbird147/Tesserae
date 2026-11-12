"""Build a Quackle DAWG from a text word list.

    F:\\Python312\\python.exe tools\\make_dawg.py words.txt data\\enable.dawg

The word list is read as one word per line, uppercased, sorted, and limited to
2-15 letters. The cleaned list is written next to the DAWG (same name, .txt) so
the game always has the exact words that the engine is using.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tessera.dawg import build_dawg, normalise, read_dawg_words  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    source, target = argv[1], argv[2]
    with open(source, "r", encoding="utf-8", errors="ignore") as handle:
        words = normalise(handle)
    if not words:
        print("no usable words in", source)
        return 1
    clean = os.path.splitext(target)[0] + ".txt"
    with open(clean, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(words) + "\n")
    nodes = build_dawg(words, target)
    back = read_dawg_words(target)
    ok = set(back) == set(words)
    print(f"{os.path.basename(target)}: {len(words)} words, {nodes} nodes, "
          f"{os.path.getsize(target)} bytes, readback {'ok' if ok else 'MISMATCH'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
