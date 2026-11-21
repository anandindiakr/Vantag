import argparse
import hashlib
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


def prepare_offline_bundle() -> list[str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    keys_file = ROOT / "offline_keys.json"
    if not keys_file.is_file():
        keys_file = ROOT / "assets" / "offline_keys.json"
    if not keys_file.is_file():
        raise FileNotFoundError("Provide offline public verification keys; never bundle a signing private key")
    keys = json.loads(keys_file.read_text(encoding="utf-8"))
    if not isinstance(keys, dict) or not keys:
        raise ValueError("At least one offline verification key is required")
    for name, pem in keys.items():
        if not isinstance(name, str) or not isinstance(pem, str) or not isinstance(serialization.load_pem_public_key(pem.encode()), Ed25519PublicKey):
            raise ValueError("Offline keys must be named Ed25519 public keys; never bundle a private key")
    subprocess.run(["npm.cmd", "run", "build:offline"], cwd=REPO / "frontend" / "web", check=True)
    ui = REPO / "frontend" / "web" / "dist-offline"
    if not (ui / "offline.html").is_file() or not (ui / "assets").is_dir():
        raise FileNotFoundError("Build the offline console assets first")
    hashes = {}
    for name in ("yolo26n.onnx", "yolov8n-pose.onnx", "yolov8s-worldv2.pt", "hand_landmarker.task"):
        with (BUILD_MODELS / name).open("rb") as source:
            hashes[name] = hashlib.file_digest(source, "sha256").hexdigest()
    (BUILD_MODELS / "offline-manifest.json").write_text(json.dumps({"version": 1, "sha256": hashes}, indent=2), encoding="utf-8")
    return [
        "--add-data", f"{ui}{os.pathsep}offline-ui",
        "--add-data", f"{keys_file}{os.pathsep}.",
        "--collect-all", "cryptography", "--collect-all", "fastapi",
        "--collect-all", "uvicorn", "--collect-all", "tzdata",
        "--hidden-import", "agent.local.desktop",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.asyncio",
        "--hidden-import", "uvicorn.protocols.http.h11_impl",
        "--hidden-import", "uvicorn.lifespan.on",
    ]


def write_offline_launch_config(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.json").write_text(json.dumps({"mode": "offline"}), encoding="utf-8")
    (directory / "START-OFFLINE.cmd").write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0VantagAgent.exe" --offline\r\n')


def create_archive(output: Path, archive_path: Path, *, offline: bool) -> None:
    if offline and json.loads((output / "config.json").read_text(encoding="utf-8")) != {"mode": "offline"}:
        raise ValueError("Offline archive configuration must contain only the offline mode")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=True) as archive:
        for path in output.rglob("*"):
            if path.is_file() and path.resolve() != archive_path.resolve():
                relative = path.relative_to(output).as_posix()
                if relative == "config.json" and not offline:
                    continue
                archive.write(path, relative)


def build(offline: bool = False):
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("Build using the dedicated 64-bit Python 3.11 environment")
    os.environ["YOLO_AUTOINSTALL"] = "false"
    prepare_models()
    offline_arguments = prepare_offline_bundle() if offline else []
    output_dir = OUTPUT_DIR / "offline" if offline else OUTPUT_DIR
    output = output_dir / "VantagAgent"
    archive_path = output_dir / ("windows-offline-agent.zip" if offline else "windows-agent.zip")
    (ROOT / "agent" / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "assets" / "icon.ico", ROOT / "agent" / "assets" / "icon.ico")
    spec_dir = ROOT / "build" / "standalone_spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--name", "VantagAgent", "--onedir",
        "--windowed", "--noconfirm", "--noupx", "--icon", str(ROOT / "assets" / "icon.ico"),
        "--distpath", str(output_dir), "--workpath", str(ROOT / "build" / "standalone_work"),
        "--specpath", str(spec_dir),
        "--hidden-import", "pystray._win32", "--hidden-import", "onnxruntime",
        "--collect-all", "ultralytics", "--collect-all", "mediapipe",
        "--collect-all", "onnxruntime", "--collect-all", "cv2", "--collect-binaries", "torchvision",
        "--add-data", f"{BUILD_MODELS}{os.pathsep}models",
        "--add-data", f"{ROOT / 'agent' / 'assets'}{os.pathsep}agent/assets",
        *offline_arguments,
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
        shutil.copyfile(source, output / "_internal" / "torchvision" / name)
    sys.path.insert(0, str(ROOT))
    from agent import __version__

    if offline:
        write_offline_launch_config(output)

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
            [str(output / "VantagAgent.exe"), "--offline-smoke-test" if offline else "--smoke-test", str(result_file)],
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
            [str(output / "VantagAgent.exe"), "--ui-test", str(ui_result_file)],
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

    create_archive(output, archive_path, offline=offline)
    with zipfile.ZipFile(archive_path, "a", compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=True) as archive:
        archive.writestr("PACKAGE_VERSION.txt", __version__)
        if offline:
            archive.writestr("OFFLINE_CAPABILITIES.json", json.dumps({
                "version": __version__, "disconnected_core_validated": False,
                "commercial_redistribution_approved": False,
                "status": "development; not qualified for customer distribution",
                "unavailable": ["staff_matching", "visual_verification", "visual_search", "assistant", "high_value_counter"],
            }, indent=2))
    print(f"Package: {archive_path}")
    print(f"Compressed bytes: {archive_path.stat().st_size}")
    print(f"Extracted bytes: {sum(path.stat().st_size for path in output.rglob('*') if path.is_file())}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-bundle", action="store_true")
    build(offline=parser.parse_args().offline_bundle)
