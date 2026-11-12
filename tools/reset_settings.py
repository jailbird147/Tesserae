import json
import os

path = os.path.join(os.environ.get("APPDATA", ""), "Tessera", "settings.json")
defaults = {
    "name": "Player",
    "opponents": 1,
    "turn_seconds": 120,
    "allow_blank_recycle": True,
    "allow_hints": True,
    "lexicon": "csw",
    "fullscreen": False,
    "highlight_last_move": True,
    "port": "5467",
}
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as handle:
    json.dump(defaults, handle, indent=2)
print("reset", path)
