import io

path = r"F:\AI Scrabble\data\CSW24.txt"
words = [line.strip() for line in io.open(path, encoding="utf-8") if line.strip()]
print("count", len(words))
print("first", words[:6])
print("last", words[-6:])
print("longest", max(len(w) for w in words))
print("all alpha", all(w.isalpha() for w in words))
print("two-letter", len([w for w in words if len(w) == 2]))
