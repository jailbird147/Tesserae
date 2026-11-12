"""Word lists: the built-in CSW24 / SOWPODS / ENABLE lists, plus imported ones.

Built-in lists ship with the game. Imported lists ("my club list") live in
%APPDATA%\\Tessera\\wordlists as a cleaned .txt and a matching .dawg, so the
engine and the rules always use exactly the same words.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time

from .dawg import build_dawg, normalise, read_dawg_words

# label, text file and DAWG path (paths are relative to the game folder)
BUILTIN: dict[str, dict] = {
    "csw": {
        "file": "data/CSW24.txt",
        "dawg": "data/csw24.dawg",
        "label": "CSW24",
        "note": "Collins Scrabble Words 2024",
    },
    "sowpods": {
        "file": "data/SOWPODS.txt",
        "dawg": "data/sowpods.dawg",
        "label": "SOWPODS",
        "note": "Collin 2007 list, for old games",
    },
    "enable": {
        "file": "data/enable.txt",
        "dawg": "data/enable.dawg",
        "label": "ENABLE",
        "note": "Free public-domain word list",
    },
}

# Which Quackle strategy data to use for a list (only two exist: CSW and SOWPODS)
STRATEGY_FOR = {"csw": "csw", "sowpods": "sowpods"}

KNOWN_HASHES = {
    "csw": "F1397AC46AAECA388119B195B126CAEA7BFFABE40F86FA6188A8A48F44347BEC",
    "sowpods": "9EA522607CEB20BB755F127906CE9127ACB80235E7451B1E2C6329460979F7B8",
}

MIN_WORDS = 500
MAX_BYTES = 40 * 1024 * 1024


class Lexicon:
    def __init__(self, words: set[str], name: str = "csw") -> None:
        self.words = words
        self.name = name
        self.max_length = max((len(w) for w in words), default=15)

    @property
    def label(self) -> str:
        return lexicon_label(self.name)

    def contains(self, word: str) -> bool:
        return word.upper() in self.words

    def __len__(self) -> int:
        return len(self.words)


_cache: dict[str, Lexicon] = {}
_hashes: dict[str, str] = {}
_custom_cache: dict[str, dict] | None = None


# --------------------------------------------------------------------- folders
def game_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_path(*parts: str) -> str:
    return os.path.join(game_root(), *parts)


def wordlist_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "Tessera", "wordlists")
    os.makedirs(path, exist_ok=True)
    return path


def _custom_meta_path() -> str:
    return os.path.join(wordlist_dir(), "wordlists.json")


def _read_custom_meta() -> dict[str, dict]:
    global _custom_cache
    if _custom_cache is not None:
        return _custom_cache
    try:
        with open(_custom_meta_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _custom_cache = {k: v for k, v in data.items() if isinstance(v, dict)}
        else:
            _custom_cache = {}
    except (OSError, ValueError):
        _custom_cache = {}
    # A list whose files have gone is not usable.
    for name in list(_custom_cache):
        entry = _custom_cache[name]
        if not os.path.exists(_txt_path(name)) or not os.path.exists(_dawg_path(name)):
            del _custom_cache[name]
    return _custom_cache


def _write_custom_meta(meta: dict[str, dict]) -> None:
    global _custom_cache
    _custom_cache = meta
    try:
        with open(_custom_meta_path(), "w", encoding="utf-8") as handle:
            json.dump(meta, handle, indent=2, sort_keys=True)
    except OSError:
        pass


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "custom"


def _txt_path(name: str) -> str:
    return os.path.join(wordlist_dir(), f"{name}.txt")


def _dawg_path(name: str) -> str:
    return os.path.join(wordlist_dir(), f"{name}.dawg")


# ------------------------------------------------------------------- registry
def custom_lexicons() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, entry in _read_custom_meta().items():
        out[name] = {
            "file": _txt_path(name),
            "dawg": _dawg_path(name),
            "label": entry.get("label") or name.title(),
            "note": entry.get("note") or f"Imported {entry.get('imported', '')}".strip(),
            "custom": True,
            "words": entry.get("words", 0),
        }
    return out


def all_lexicons() -> dict[str, dict]:
    """Built-in lists that are actually present, plus every imported list."""
    out: dict[str, dict] = {}
    for name, entry in BUILTIN.items():
        if os.path.exists(data_path(entry["file"])) and os.path.exists(data_path(entry["dawg"])):
            out[name] = dict(entry)
    out.update(custom_lexicons())
    return out


def lexicon_names() -> list[str]:
    return list(all_lexicons().keys())


def default_lexicon() -> str:
    names = lexicon_names()
    for candidate in ("csw", "enable", "sowpods"):
        if candidate in names:
            return candidate
    return names[0] if names else "csw"


def resolve(name: str | None) -> str:
    available = all_lexicons()
    if name and name in available:
        return name
    return default_lexicon()


def _entry(name: str) -> dict:
    available = all_lexicons()
    return available.get(resolve(name), {})


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else data_path(path)


def lexicon_dawg(name: str) -> str:
    return _abs(_entry(name).get("dawg", BUILTIN["csw"]["dawg"]))


def lexicon_file(name: str) -> str:
    return _abs(_entry(name).get("file", BUILTIN["csw"]["file"]))


def lexicon_label(name: str) -> str:
    return _entry(name).get("label") or "CSW24"


def lexicon_note(name: str) -> str:
    return _entry(name).get("note", "")


def strategy_lexicon(name: str) -> str:
    """Quackle names its strategy data after a lexicon; imported lists reuse CSW."""
    return STRATEGY_FOR.get(resolve(name), "csw")


# --------------------------------------------------------------------- hashes
def _file_hash(name: str) -> str:
    if name not in _hashes:
        try:
            with open(lexicon_file(name), "rb") as handle:
                _hashes[name] = hashlib.sha256(handle.read()).hexdigest().upper()
        except OSError:
            _hashes[name] = ""
    return _hashes[name]


def lexicon_identity(name: str = "csw") -> dict:
    """Name, word count and SHA-256 of the list file, so a game can be tied to
    an exact list. Imported lists are shown as CUSTOM, not VERIFIED."""
    name = resolve(name)
    entry = _entry(name)
    lexicon = load_lexicon(name)
    digest = _file_hash(name)
    custom = bool(entry.get("custom"))
    return {
        "name": name,
        "label": lexicon.label,
        "file": os.path.basename(lexicon_file(name)),
        "words": len(lexicon),
        "sha256": digest,
        "custom": custom,
        "verified": (not custom) and bool(digest) and digest == KNOWN_HASHES.get(name),
    }


# --------------------------------------------------------------------- loading
def load_lexicon(name: str = "csw", path: str | None = None) -> Lexicon:
    name = resolve(name)
    if path is None and name in _cache:
        return _cache[name]

    path = path or lexicon_file(name)
    words: set[str] = set()
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            word = line.strip().upper()
            if word and word.isalpha():
                words.add(word)
    lexicon = Lexicon(words, name)
    if path == lexicon_file(name):
        _cache[name] = lexicon
    return lexicon


# -------------------------------------------------------------------- imports
def import_wordlist(source: str, label: str = "") -> dict:
    """Copy, clean and compile a word list. Returns the identity of the new list.

    Raises ValueError with a readable message if the file is unusable.
    """
    source = os.path.expandvars(os.path.expanduser((source or "").strip().strip('"')))
    if not source:
        raise ValueError("Choose a word list file first.")
    if not os.path.isfile(source):
        raise ValueError("That file was not found.")
    if os.path.getsize(source) > MAX_BYTES:
        raise ValueError("That file is too big for a word list.")
    if not source.lower().endswith((".txt", ".dic", ".words", ".list")):
        # Still try: people rename these constantly.
        pass

    with open(source, "r", encoding="utf-8", errors="ignore") as handle:
        words = normalise(handle)
    if len(words) < MIN_WORDS:
        raise ValueError(
            f"That list has only {len(words):,} usable words. "
            f"At least {MIN_WORDS:,} words of 2-15 letters are needed."
        )

    name = label.strip() or os.path.splitext(os.path.basename(source))[0]
    name = name.strip() or "My list"
    slug = _slug(name)
    meta = dict(_read_custom_meta())
    existing = {k for k in meta}
    while slug in existing:
        slug = f"{slug}-2" if not slug.endswith("-2") else slug[:-2] + "-3"
    # Never shadow a built-in list.
    while slug in BUILTIN:
        slug = f"{slug}-custom"

    txt_path = _txt_path(slug)
    with open(txt_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(words) + "\n")
    nodes = build_dawg(words, _dawg_path(slug))
    back = set(read_dawg_words(_dawg_path(slug)))
    if back != set(words):
        raise ValueError("The word list could not be compiled for the engine.")

    digest = hashlib.sha256(open(txt_path, "rb").read()).hexdigest().upper()
    meta[slug] = {
        "label": name,
        "source": os.path.basename(source),
        "words": len(words),
        "nodes": nodes,
        "sha256": digest,
        "imported": time.strftime("%Y-%m-%d"),
    }
    _write_custom_meta(meta)
    reset_cache()
    return lexicon_identity(slug)


def delete_wordlist(name: str) -> bool:
    meta = dict(_read_custom_meta())
    if name not in meta:
        return False
    del meta[name]
    _write_custom_meta(meta)
    for path in (_txt_path(name), _dawg_path(name)):
        try:
            os.remove(path)
        except OSError:
            pass
    reset_cache()
    return True


def reset_cache() -> None:
    global _custom_cache, _hashes
    _cache.clear()
    _hashes.clear()
    _custom_cache = None
