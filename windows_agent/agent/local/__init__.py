import os


def configure_offline_environment() -> None:
    os.environ.update({
        "YOLO_OFFLINE": "1",
        "YOLO_AUTOINSTALL": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
    })
