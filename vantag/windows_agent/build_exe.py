"""
Build the Vantag Windows Edge Agent as a standalone .exe using PyInstaller.

Requirements:
  - Python 3.11 or 3.12  (PyInstaller does not yet support 3.14)
  - pip install pyinstaller pillow

Usage:
    python build_exe.py

Output: dist/VantagAgent/VantagAgent.exe
Then ZIP and upload: dist/VantagAgent/  (the whole folder)
"""
import subprocess
import sys
import struct
from pathlib import Path

ROOT = Path(__file__).parent
ASSETS_DIR = ROOT / "assets"
ICON_PATH = ASSETS_DIR / "icon.ico"


def check_python_version():
    major, minor = sys.version_info[:2]
    if major != 3 or minor > 12:
        print(f"[WARNING] Python {major}.{minor} detected.")
        print("  PyInstaller works best with Python 3.11 or 3.12.")
        print("  Python 3.13+ may have compatibility issues.")
        print("  Consider installing Python 3.11: https://www.python.org/downloads/release/python-3119/")
        resp = input("  Continue anyway? (y/N): ").strip().lower()
        if resp != "y":
            sys.exit(1)


def generate_icon():
    """Generate a minimal valid .ico file programmatically (no external tools needed)."""
    ASSETS_DIR.mkdir(exist_ok=True)
    if ICON_PATH.exists():
        print(f"[OK] Icon found: {ICON_PATH}")
        return

    print("[*] Generating icon (no assets/icon.ico found)...")
    try:
        from PIL import Image, ImageDraw
        # Violet shield icon matching the tray icon style
        sizes = [256, 128, 64, 48, 32, 16]
        images = []
        for size in sizes:
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            pad = size // 8
            draw.rounded_rectangle(
                [pad, pad // 2, size - pad, size - pad],
                radius=size // 8,
                fill=(139, 92, 246),
            )
            cx, cy, r = size // 2, size // 2, size // 6
            draw.ellipse([cx - r, cy - r - size // 10, cx + r, cy + r - size // 10],
                         fill=(255, 255, 255))
            images.append(img)
        images[0].save(str(ICON_PATH), format="ICO", sizes=[(s, s) for s in sizes],
                       append_images=images[1:])
        print(f"[OK] Icon generated: {ICON_PATH}")
    except ImportError:
        print("[WARNING] Pillow not installed — building without icon")
        return None
    return ICON_PATH


def build():
    check_python_version()
    icon = generate_icon()

    # Bundle the config template alongside the exe
    cfg_template = ROOT / "config.template.json"
    if not cfg_template.exists():
        print("[WARNING] config.template.json not found — skipping bundle")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "VantagAgent",
        "--onedir",
        "--windowed",           # No console window (runs via tray icon)
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "onnxruntime",
        "--hidden-import", "schedule",
        "--hidden-import", "psutil",
        "--collect-submodules", "onnxruntime",
        "--collect-submodules", "cv2",
        "--noconfirm",
        "--clean",
    ]

    # Add icon if generated/found
    if icon and icon.exists():
        cmd += ["--icon", str(icon)]
        cmd += ["--add-data", f"{ASSETS_DIR};assets"]

    # Bundle config template so users can rename it
    if cfg_template.exists():
        cmd += ["--add-data", f"{cfg_template};."]

    cmd.append("agent/main.py")

    print("\n" + "=" * 60)
    print("Building VantagAgent.exe (this takes 2-5 minutes)...")
    print("=" * 60 + "\n")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        exe = ROOT / "dist" / "VantagAgent" / "VantagAgent.exe"
        print("\n" + "=" * 60)
        print("[SUCCESS] Build complete!")
        print(f"  EXE: {exe}")
        print(f"  DIR: {exe.parent}")
        print("\nNext steps:")
        print("  1. Copy config.template.json into dist/VantagAgent/ and rename to config.json")
        print("  2. Set api_key in config.json")
        print("  3. ZIP the entire dist/VantagAgent/ folder")
        print("  4. Upload the ZIP to your VPS or distribute to store staff")
        print("=" * 60)
    else:
        print("\n[FAILED] Build failed — check output above")
        print("\nCommon fixes:")
        print("  - Wrong Python version: use 3.11 or 3.12")
        print("  - Missing PyInstaller: pip install pyinstaller")
        print("  - Missing Pillow: pip install pillow")
        sys.exit(1)


if __name__ == "__main__":
    build()
