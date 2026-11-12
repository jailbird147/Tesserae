import os
import shutil

SRC = r"F:\OpenCode\Projects\Tessera\assets\brand"
DST = r"F:\Tessera\assets"
os.makedirs(DST, exist_ok=True)

for source_name, target_name in (("app.ico", "app.ico"), ("icon-preview-256.png", "icon.png")):
    source = os.path.join(SRC, source_name)
    if os.path.exists(source):
        shutil.copy2(source, os.path.join(DST, target_name))
        print("copied", target_name)
    else:
        print("missing", source)

print(os.listdir(DST))
