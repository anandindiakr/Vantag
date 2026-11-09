import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
BUILD_MODELS = ROOT / "build" / "standalone_models"
OUTPUT_DIR = ROOT / "build" / "standalone_output"
OUTPUT = OUTPUT_DIR / "VantagAgent"
ARCHIVE = OUTPUT_DIR / "windows-agent.zip"
WORLD_URL = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8s-worldv2.pt"


def prepare_models():
    import onnxruntime as ort
    import requests
    from ultralytics import YOLO

    BUILD_MODELS.mkdir(parents=True, exist_ok=True)
    for weights, expected in (("yolo26n.pt", [1, 300, 6]), ("yolov8n-pose.pt", [1, 56, 8400])):
        source = REPO / "models" / weights
        if not source.is_file():
            raise FileNotFoundError(f"Required source weights missing: {source}")
        target_weights = BUILD_MODELS / weights
        shutil.copyfile(source, target_weights)
        model = YOLO(str(target_weights))
        options = {"format": "onnx", "imgsz": 640, "dynamic": False, "nms": False}
        if weights == "yolo26n.pt":
            options.update(opset=19, simplify=True)
        else:
            options.update(opset=12, simplify=False)
        exported = Path(model.export(**options))
        session = ort.InferenceSession(str(exported), providers=["CPUExecutionProvider"])
        shape = session.get_outputs()[0].shape
        if shape != expected:
            raise RuntimeError(f"Unexpected {weights} output shape: {shape}; expected {expected}")
        del session
    shutil.copyfile(REPO / "models" / "hand_landmarker.task", BUILD_MODELS / "hand_landmarker.task")
    world = BUILD_MODELS / "yolov8s-worldv2.pt"
    if not world.is_file():
        temporary = world.with_suffix(".part")
        with requests.get(WORLD_URL, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    output.write(chunk)
        temporary.replace(world)
    YOLO(str(world))


def build():
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("Build using the dedicated 64-bit Python 3.11 environment")
    os.environ["YOLO_AUTOINSTALL"] = "false"
    prepare_models()
    (ROOT / "agent" / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "assets" / "icon.ico", ROOT / "agent" / "assets" / "icon.ico")
    spec_dir = ROOT / "build" / "standalone_spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--name", "VantagAgent", "--onedir",
        "--windowed", "--noconfirm", "--noupx", "--icon", str(ROOT / "assets" / "icon.ico"),
        "--distpath", str(OUTPUT_DIR), "--workpath", str(ROOT / "build" / "standalone_work"),
        "--specpath", str(spec_dir),
        "--hidden-import", "pystray._win32", "--hidden-import", "onnxruntime",
        "--collect-all", "ultralytics", "--collect-all", "mediapipe",
        "--collect-all", "onnxruntime", "--collect-all", "cv2", "--collect-binaries", "torchvision",
        "--add-data", f"{BUILD_MODELS}{os.pathsep}models",
        "--add-data", f"{ROOT / 'agent' / 'assets'}{os.pathsep}agent/assets",
        str(ROOT / "standalone_entry.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    torchvision = importlib.util.find_spec("torchvision")
    if torchvision is None or not torchvision.origin:
        raise RuntimeError("torchvision is required for the standalone product counter")
    torchvision_dir = Path(torchvision.origin).parent
    for name in ("_C_stable.pyd", "image_stable.pyd"):
        source = torchvision_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"Required torchvision extension missing: {source}")
        shutil.copyfile(source, OUTPUT / "_internal" / "torchvision" / name)
    sys.path.insert(0, str(ROOT))
    from agent import __version__

    with tempfile.TemporaryDirectory(prefix="vantag-standalone-smoke-") as temporary:
        result_file = Path(temporary) / "result.json"
        environment = os.environ.copy()
        environment.update({
            "PATH": str(Path(os.environ["SYSTEMROOT"]) / "System32"),
            "APPDATA": temporary,
            "LOCALAPPDATA": temporary,
            "USERPROFILE": temporary,
            "YOLO_AUTOINSTALL": "false",
        })
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        process = subprocess.run(
            [str(OUTPUT / "VantagAgent.exe"), "--smoke-test", str(result_file)],
            cwd=temporary,
            env=environment,
            timeout=600,
            check=False,
        )
        if not result_file.is_file():
            raise RuntimeError(f"Packaged smoke test did not report a result (exit {process.returncode})")
        result = json.loads(result_file.read_text(encoding="utf-8"))
        if process.returncode != 0 or not result.get("ok") or not result.get("frozen") or result.get("version") != __version__:
            raise RuntimeError(f"Packaged smoke test failed: {result}")
        print(f"Packaged smoke test passed: {result}")

        ui_result_file = Path(temporary) / "ui-result.json"
        ui_process = subprocess.run(
            [str(OUTPUT / "VantagAgent.exe"), "--ui-test", str(ui_result_file)],
            cwd=temporary,
            env=environment,
            timeout=60,
            check=False,
        )
        if not ui_result_file.is_file():
            raise RuntimeError(f"Packaged UI smoke test did not report a result (exit {ui_process.returncode})")
        ui_result = json.loads(ui_result_file.read_text(encoding="utf-8"))
        if ui_process.returncode != 0 or not ui_result.get("ok") or ui_result.get("title") != "Vantag Edge Agent" or "test-camera" not in ui_result.get("cameras", []):
            raise RuntimeError(f"Packaged UI smoke test failed: {ui_result}")
        print(f"Packaged UI smoke test passed: {ui_result}")

    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=True) as archive:
        for path in OUTPUT.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(OUTPUT).as_posix())
        archive.writestr("PACKAGE_VERSION.txt", __version__)
    print(f"Package: {ARCHIVE}")
    print(f"Compressed bytes: {ARCHIVE.stat().st_size}")
    print(f"Extracted bytes: {sum(path.stat().st_size for path in OUTPUT.rglob('*') if path.is_file())}")


if __name__ == "__main__":
    build()
