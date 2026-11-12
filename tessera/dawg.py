"""Build Quackle DAWG files from a plain word list.

The engine reads dictionaries in Quackle's version-1 DAWG format:

    byte 0        version (1)
    bytes 1-16    hash, used by Quackle to match a GADDAG to its DAWG
    bytes 17-19   word count, big endian
    byte 20       alphabet length, then each letter followed by a space
    ...           nodes, seven bytes each

Each node is a 24-bit pointer to the first of its children (0 = no children),
one byte holding the letter and two flags, and a 24-bit playability value.
A node ends a word when its playability is not zero. Children are stored as a
contiguous block; the last child carries the "lastchild" flag. The root node is
index 0 and its letter byte is ignored.

Building the layout ourselves means a player can import any word list without
needing a compiler or a copy of Quackle's own tools.
"""

from __future__ import annotations

import hashlib
import os

FIRST_LETTER = ord("A")
MAX_WORD_LENGTH = 15  # longer words can never fit on the board


def normalise(words) -> list[str]:
    """Uppercase, A-Z only, sorted, deduplicated, board-length words."""
    seen: set[str] = set()
    for word in words:
        word = word.strip().upper()
        if 2 <= len(word) <= MAX_WORD_LENGTH and word.isalpha() and word.isascii():
            seen.add(word)
    return sorted(seen)


class _Trie:
    def __init__(self) -> None:
        self.children: list[dict[int, int]] = [{}]
        self.letter: list[int] = [0]
        self.terminal: list[bool] = [False]

    def add(self, word: str) -> None:
        node = 0
        for char in word:
            code = ord(char) - FIRST_LETTER
            if not 0 <= code < 26:
                return
            child = self.children[node].get(code)
            if child is None:
                child = len(self.children)
                self.children[node][code] = child
                self.children.append({})
                self.letter.append(code)
                self.terminal.append(False)
            node = child
        self.terminal[node] = True


def build_dawg(words, path: str) -> int:
    """Write `words` to `path` as a Quackle DAWG. Returns the node count."""
    trie = _Trie()
    entries = normalise(words)
    for word in entries:
        trie.add(word)

    # Breadth-first numbering: a node's children always sit in one block, and
    # the highest-coded child carries the lastchild flag.
    order = [0]
    position = {0: 0}
    for node in order:
        for code in sorted(trie.children[node]):
            child = trie.children[node][code]
            position[child] = len(order)
            order.append(child)

    last_child = [False] * len(trie.children)
    for kids in trie.children:
        if kids:
            last_child[kids[max(kids)]] = True
    last_child[0] = True

    body = bytearray()
    for node in order:
        edges = trie.children[node]
        kids = [edges[code] for code in sorted(edges)]
        pointer = position[kids[0]] if kids else 0
        flag = trie.letter[node] | (64 if last_child[node] else 0) | 128
        body += pointer.to_bytes(3, "big")
        body.append(flag)
        body += (1 if trie.terminal[node] else 0).to_bytes(3, "big")

    header = bytearray([1])
    header += hashlib.sha256("\n".join(entries).encode("utf-8")).digest()[:16]
    header += len(entries).to_bytes(3, "big")
    header.append(26)
    for index in range(26):
        header.append(FIRST_LETTER + index)
        header.append(32)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "wb") as handle:
        handle.write(bytes(header))
        handle.write(bytes(body))
    os.replace(temp, path)
    return len(order)


def read_dawg_words(path: str) -> list[str]:
    """Read a DAWG back into words, to check a built file."""
    with open(path, "rb") as handle:
        data = handle.read()
    if not data or data[0] != 1:
        raise ValueError("not a version 1 DAWG")
    alphabet_length = data[20]
    offset = 21 + alphabet_length * 2
    nodes = (len(data) - offset) // 7

    def node(index: int):
        at = offset + index * 7
        pointer = int.from_bytes(data[at : at + 3], "big")
        letter = data[at + 3] & 63
        lastchild = bool(data[at + 3] & 64)
        playability = int.from_bytes(data[at + 4 : at + 7], "big")
        return pointer, letter, lastchild, playability

    words: list[str] = []
    stack: list[tuple[int, str]] = [(0, "")]
    while stack:
        index, prefix = stack.pop()
        pointer, letter, _last, playability = node(index)
        word = "" if index == 0 else prefix + chr(FIRST_LETTER + letter)
        if playability and index != 0:
            words.append(word)
        if pointer:
            for child in range(pointer, nodes):
                stack.append((child, word))
                if node(child)[2]:
                    break
    return sorted(words)
