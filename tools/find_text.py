import io
import os
import sys

TERMS = sys.argv[1:] or ["Scrabble", "scrabble", "SCRABBLE"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {"build", "dist", "shots", "obj", "__pycache__", ".git"}

for folder, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for name in files:
        if not name.endswith((".py", ".md", ".bat", ".txt", ".cpp", ".json")):
            continue
        path = os.path.join(folder, name)
        if os.path.getsize(path) > 5_000_000:
            continue
        try:
            lines = io.open(path, encoding="utf-8", errors="ignore").read().splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if any(term in line for term in TERMS):
                print(f"{os.path.relpath(path, ROOT)}:{number}: {line.strip()[:140]}")
