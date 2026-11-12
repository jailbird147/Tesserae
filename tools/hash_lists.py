import hashlib
import os

for name in ("CSW24.txt", "SOWPODS.txt"):
    path = os.path.join(r"F:\Tessera\data", name)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest().upper()
    print(name, os.path.getsize(path), digest)
