import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
exe = os.path.join(ROOT, "dist", "Tessera", "Tessera.exe")
proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
time.sleep(12)
alive = proc.poll() is None
print("alive after 12s:", alive, "exit:", None if alive else proc.returncode)
if alive:
    proc.terminate()
    time.sleep(1)
    proc.kill()
print("ok" if alive else "FAILED")
