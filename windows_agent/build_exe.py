"""
Build the Vantag Windows Edge Agent as a standalone .exe using PyInstaller.

Usage:
    python build_exe.py

Output: dist/VantagAgent/VantagAgent.exe
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name", "VantagAgent",
    "--onedir",
    "--windowed",           # No console window (uses tray)
    "--icon", "assets/icon.ico",
    "--add-data", "assets;assets",
    "--hidden-import", "pystray._win32",
    "--hidden-import", "PIL._tkinter_finder",
    "--hidden-import", "onnxruntime",
    "--collect-submodules", "onnxruntime",
    "--collect-submodules", "cv2",
    "--noconfirm",
    "agent/main.py",
]

print("Building VantagAgent.exe...")
result = subprocess.run(cmd, cwd=str(ROOT))
if result.returncode == 0:
    print("\nBuild successful!")
    print(f"Executable: {ROOT / 'dist' / 'VantagAgent' / 'VantagAgent.exe'}")
else:
    print("\nBuild FAILED — check output above")
    sys.exit(1)
