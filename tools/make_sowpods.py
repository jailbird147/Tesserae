import io
import os

src = r"F:\quackle_src\quackle-1.1.0\data\raw_lexica\sowpods.raw"
dst = r"F:\AI Scrabble\data\SOWPODS.txt"

words = []
with open(src, "r", encoding="latin-1") as handle:
    for line in handle:
        word = line.strip().upper()
        if word and word.isalpha():
            words.append(word)

with io.open(dst, "w", encoding="utf-8", newline="\n") as handle:
    handle.write("\n".join(words) + "\n")

print(len(words), "words")
print("first", words[:5], "last", words[-5:])
print("two-letter", len([w for w in words if len(w) == 2]))
print("size", os.path.getsize(dst))
