"""
models/export/export_tensorrt.py
=================================
TensorRT export script for Vantag platform.

Converts a YOLOv8 ``.pt`` model to an ONNX intermediate and then to a
TensorRT ``.engine`` file optimised for Jetson (ARM64) deployment.

Usage
-----
::

    python export_tensorrt.py \\
        --model  models/weights/yolov8n.pt \\
        --output models/weights/yolov8n.engine \\
        --precision fp16 \\
        --workspace 4

    # Also export a companion pose model:
    python export_tensorrt.py \\
        --model  models/weights/yolov8n.pt \\
        --output models/weights/yolov8n.engine \\
        --pose   models/weights/yolov8n-pose.pt

Notes
-----
* Batch size is fixed at 1 (no dynamic shapes) for Jetson stability.
* The engine file is skipped if it already exists *and* is newer than the
  source ``.pt`` file (cache-hit behaviour).
* Build progress is shown via ``tqdm``.
"""

from __future__ import annotations

import argparse
import logging
import os
import struct
import sys
import time
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: check whether a cached engine is still fresh
# ---------------------------------------------------------------------------

def _engine_is_fresh(engine_path: Path, source_pt: Path) -> bool:
    """Return *True* if *engine_path* exists and is newer than *source_pt*."""
    engine_path = Path(engine_path)
    source_pt   = Path(source_pt)
    if not engine_path.exists():
        return False
    if not source_pt.exists():
        return True   # engine exists but source gone — treat as fresh
    engine_mtime = engine_path.stat().st_mtime
    source_mtime = source_pt.stat().st_mtime
    return engine_mtime > source_mtime


# ---------------------------------------------------------------------------
# Step 1: Export YOLO .pt → ONNX
# ---------------------------------------------------------------------------

def export_to_onnx(pt_path: Path, onnx_path: Path) -> Path:
    """
    Export a YOLOv8 ``.pt`` model to ONNX using the ``ultralytics`` library.

    Parameters
    ----------
    pt_path:
        Absolute path to the source ``.pt`` weights file.
    onnx_path:
        Desired output path for the ``.onnx`` file.

    Returns
    -------
    Path to the generated ``.onnx`` file (may differ slightly from
    *onnx_path* due to ultralytics naming conventions).
    """
    logger.info("Step 1/3 — Exporting '%s' to ONNX …", pt_path)

    try:
        from ultralytics import YOLO  # type: ignore[import]
    except ImportError as exc:
        logger.error("'ultralytics' is not installed: %s", exc)
        sys.exit(1)

    model = YOLO(str(pt_path))
    # ultralytics export() returns the path to the generated file.
    result = model.export(
        format="onnx",
        imgsz=640,
        batch=1,
        simplify=True,
        opset=17,
        dynamic=False,
    )
    generated = Path(str(result))

    # Rename / move to the requested path if different.
    if generated.resolve() != onnx_path.resolve():
        onnx_path.parent.mkdir(parents=True, exist_ok=True)
        generated.replace(onnx_path)
        logger.info("ONNX file moved to '%s'.", onnx_path)
    else:
        logger.info("ONNX file written to '%s'.", onnx_path)

    return onnx_path


# ---------------------------------------------------------------------------
# Step 2: Build TensorRT engine from ONNX
# ---------------------------------------------------------------------------

def build_trt_engine(
    onnx_path: Path,
    engine_path: Path,
    precision: str,
    workspace_gb: int,
) -> None:
    """
    Compile an ONNX model into a TensorRT serialised engine.

    Parameters
    ----------
    onnx_path:
        Path to the input ONNX model.
    engine_path:
        Destination path for the ``.engine`` file.
    precision:
        ``'fp16'`` or ``'int8'``.  INT8 requires a calibration dataset
        (not bundled here); we fall back to FP16 with a warning if INT8
        calibration data is unavailable.
    workspace_gb:
        Maximum GPU memory workspace for the TRT builder (gigabytes).
    """
    logger.info("Step 2/3 — Building TensorRT engine (precision=%s, workspace=%dGB) …",
                precision, workspace_gb)

    try:
        import tensorrt as trt  # type: ignore[import]
    except ImportError as exc:
        logger.error("'tensorrt' Python package not found: %s", exc)
        sys.exit(1)

    try:
        from tqdm import tqdm  # type: ignore[import]
    except ImportError:
        tqdm = None  # type: ignore[assignment]

    TRT_LOGGER = trt.Logger(trt.Logger.WARNING)

    builder = trt.Builder(TRT_LOGGER)
    network_flags = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    network = builder.create_network(network_flags)
    parser = trt.OnnxParser(network, TRT_LOGGER)

    logger.info("Step 2/3 — Parsing ONNX model …")
    with open(str(onnx_path), "rb") as f:
        raw = f.read()

    if not parser.parse(raw):
        errors = [parser.get_error(i) for i in range(parser.num_errors)]
        logger.error("ONNX parsing failed:\n%s", "\n".join(str(e) for e in errors))
        sys.exit(1)

    config = builder.create_builder_config()

    # Workspace: convert GB → bytes (TRT 8.x uses set_memory_pool_limit).
    workspace_bytes = workspace_gb * (1 << 30)
    if hasattr(config, "set_memory_pool_limit"):
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_bytes)
    else:
        config.max_workspace_size = workspace_bytes  # type: ignore[attr-defined]

    # Precision flags.
    if precision == "fp16":
        if builder.platform_has_fast_fp16:
            config.set_flag(trt.BuilderFlag.FP16)
            logger.info("FP16 mode enabled.")
        else:
            logger.warning("Platform does not support fast FP16; building in FP32.")
    elif precision == "int8":
        if builder.platform_has_fast_int8:
            config.set_flag(trt.BuilderFlag.INT8)
            logger.info("INT8 mode enabled (no calibrator — requires pre-calibrated weights).")
        else:
            logger.warning("Platform does not support INT8; falling back to FP16.")
            if builder.platform_has_fast_fp16:
                config.set_flag(trt.BuilderFlag.FP16)

    # Static batch size = 1; no dynamic-shape profiles needed.
    logger.info("Step 2/3 — Compiling engine (this may take several minutes) …")

    # Show a spinner / progress bar while building.
    build_done = [False]
    serialized_engine = [None]

    def _build_blocking():
        # TRT 8.x API
        serialized = builder.build_serialized_network(network, config)
        serialized_engine[0] = serialized
        build_done[0] = True

    import threading
    build_thread = threading.Thread(target=_build_blocking, daemon=True)
    build_thread.start()

    if tqdm is not None:
        with tqdm(
            total=None,
            desc="Building TRT engine",
            unit="s",
            bar_format="{desc}: {elapsed}s elapsed",
        ) as pbar:
            while not build_done[0]:
                time.sleep(1)
                pbar.update(1)
    else:
        while not build_done[0]:
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(2)
        print()  # newline

    build_thread.join()

    if serialized_engine[0] is None:
        logger.error("TensorRT engine build failed — builder returned None.")
        sys.exit(1)

    engine_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(engine_path), "wb") as f:
        f.write(serialized_engine[0])

    size_mb = engine_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Step 2/3 — Engine written to '%s' (%.1f MB).", engine_path, size_mb
    )


# ---------------------------------------------------------------------------
# Main export pipeline
# ---------------------------------------------------------------------------

def export_model(
    pt_path: Path,
    engine_path: Path,
    precision: str,
    workspace_gb: int,
) -> None:
    """
    Full pipeline: ``.pt`` → ONNX → TensorRT ``.engine``.

    Skips the entire pipeline if a fresh engine already exists.
    """
    if _engine_is_fresh(engine_path, pt_path):
        logger.info(
            "Cache hit — '%s' is up to date. Skipping rebuild.", engine_path
        )
        return

    onnx_path = engine_path.with_suffix(".onnx")

    # --- Step 1: ONNX export ---
    onnx_path = export_to_onnx(pt_path, onnx_path)

    # --- Step 2: TRT engine build ---
    build_trt_engine(onnx_path, engine_path, precision, workspace_gb)

    # --- Step 3: Validate engine exists ---
    if not engine_path.exists():
        logger.error("Engine file was not created at '%s'.", engine_path)
        sys.exit(1)

    logger.info(
        "Step 3/3 — Validation OK. Engine ready at '%s'.", engine_path
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="export_tensorrt",
        description=(
            "Convert a YOLOv8 .pt model to a TensorRT .engine file "
            "optimised for Jetson (batch=1, no dynamic shapes)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--model",
        required=True,
        metavar="PATH",
        help="Path to the source YOLOv8 .pt weights file.",
    )
    p.add_argument(
        "--output",
        required=True,
        metavar="PATH",
        help="Destination path for the output .engine file.",
    )
    p.add_argument(
        "--precision",
        choices=["fp16", "int8"],
        default="fp16",
        help="TensorRT precision mode.",
    )
    p.add_argument(
        "--workspace",
        type=int,
        default=4,
        metavar="GB",
        help="Maximum GPU workspace memory for the TRT builder (gigabytes).",
    )
    p.add_argument(
        "--pose",
        metavar="PATH",
        default=None,
        help=(
            "If provided, also export this YOLOv8-pose .pt model. "
            "The engine will be placed alongside --output with a '-pose' suffix."
        ),
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    pt_path = Path(args.model).resolve()
    engine_path = Path(args.output).resolve()

    if not pt_path.exists():
        logger.error("Model file not found: '%s'", pt_path)
        sys.exit(1)

    # --- Primary model ---
    logger.info("=" * 60)
    logger.info("Vantag TensorRT Export — primary model")
    logger.info("  Source   : %s", pt_path)
    logger.info("  Output   : %s", engine_path)
    logger.info("  Precision: %s", args.precision)
    logger.info("  Workspace: %d GB", args.workspace)
    logger.info("=" * 60)

    export_model(pt_path, engine_path, args.precision, args.workspace)

    # --- Optional pose model ---
    if args.pose:
        pose_pt = Path(args.pose).resolve()
        if not pose_pt.exists():
            logger.error("Pose model file not found: '%s'", pose_pt)
            sys.exit(1)

        # Derive pose engine path: same stem with '-pose' appended.
        pose_engine = engine_path.with_name(
            engine_path.stem + "-pose" + engine_path.suffix
        )

        logger.info("=" * 60)
        logger.info("Vantag TensorRT Export — pose model")
        logger.info("  Source   : %s", pose_pt)
        logger.info("  Output   : %s", pose_engine)
        logger.info("  Precision: %s", args.precision)
        logger.info("  Workspace: %d GB", args.workspace)
        logger.info("=" * 60)

        export_model(pose_pt, pose_engine, args.precision, args.workspace)

    logger.info("All exports complete.")


if __name__ == "__main__":
    main()
