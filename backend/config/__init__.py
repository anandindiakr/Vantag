"""
backend/config/__init__.py
==========================
Configuration loader for the Vantag platform.

Exposes a single ``load_config()`` function that reads and merges the
``cameras.yaml`` file located in the same directory as this module.

Usage
-----
::

    from backend.config import load_config

    config = load_config()
    global_cfg = config["global"]
    cameras     = config["cameras"]

Caching
-------
The YAML file is parsed once per process.  To force a re-read (e.g. after
a hot-reload in development), call :func:`reload_config`.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).parent
_CAMERAS_YAML = _CONFIG_DIR / "cameras.yaml"


# ---------------------------------------------------------------------------
# Internal loader
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Dict[str, Any]:
    """Parse a YAML file and return its contents as a dict."""
    if not path.exists():
        logger.warning(
            "Vantag config: '%s' not found — returning empty config.", path
        )
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    logger.info("Vantag config: loaded '%s'.", path)
    return data


def _merge_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply environment-variable overrides to the config dict.

    Environment variables take the form ``VANTAG_<KEY>=<value>`` and
    override the corresponding ``global.<key>`` setting.

    Supported overrides:

    =========================== ==============================
    Environment variable        Config path
    =========================== ==============================
    ``MQTT_BROKER``             ``global.mqtt_broker``
    ``MQTT_PORT``               ``global.mqtt_port``
    ``VANTAG_ENV``              ``global.env``
    =========================== ==============================
    """
    g = config.setdefault("global", {})

    mqtt_broker = os.environ.get("MQTT_BROKER")
    if mqtt_broker:
        g["mqtt_broker"] = mqtt_broker

    mqtt_port = os.environ.get("MQTT_PORT")
    if mqtt_port:
        try:
            g["mqtt_port"] = int(mqtt_port)
        except ValueError:
            logger.warning(
                "Vantag config: MQTT_PORT='%s' is not a valid integer — ignored.",
                mqtt_port,
            )

    vantag_env = os.environ.get("VANTAG_ENV")
    if vantag_env:
        g["env"] = vantag_env

    return config


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_cached_config: Optional[Dict[str, Any]] = None


def load_config(cameras_yaml: Optional[str] = None) -> Dict[str, Any]:
    """
    Load and return the Vantag configuration dictionary.

    The configuration is cached after the first successful load; subsequent
    calls return the same object without re-reading the file.

    Parameters
    ----------
    cameras_yaml:
        Override path to the cameras YAML file.  If ``None``, defaults to
        ``backend/config/cameras.yaml`` (relative to this module).

    Returns
    -------
    dict with keys:
        * ``"global"`` — global platform settings (MQTT broker, frame
          buffer size, scoring window, etc.)
        * ``"cameras"`` — list of camera configuration dicts.
    """
    global _cached_config

    if _cached_config is not None:
        return _cached_config

    # Allow overriding the config file via VANTAG_CAMERAS_YAML env var
    # (useful for SaaS / VPS deployments to start with zero hardcoded cameras).
    env_override = os.environ.get("VANTAG_CAMERAS_YAML")
    if cameras_yaml:
        yaml_path = Path(cameras_yaml)
    elif env_override:
        yaml_path = Path(env_override)
    else:
        yaml_path = _CAMERAS_YAML
    config = _load_yaml(yaml_path)

    # Ensure expected top-level keys are present with safe defaults.
    config.setdefault("global", {})
    config.setdefault("cameras", [])

    # Apply environment-variable overrides.
    config = _merge_env_overrides(config)

    _cached_config = config
    return config


def reload_config(cameras_yaml: Optional[str] = None) -> Dict[str, Any]:
    """
    Invalidate the cache and reload the configuration from disk.

    Parameters
    ----------
    cameras_yaml:
        Override path to the cameras YAML file.

    Returns
    -------
    Freshly loaded config dict.
    """
    global _cached_config
    _cached_config = None
    logger.info("Vantag config: cache invalidated — reloading.")
    return load_config(cameras_yaml)


def get_camera_configs() -> List[Dict[str, Any]]:
    """
    Convenience wrapper that returns the ``cameras`` list from the config.

    Returns
    -------
    List of camera configuration dicts (may be empty).
    """
    return load_config().get("cameras", [])


def get_global_config() -> Dict[str, Any]:
    """
    Convenience wrapper that returns the ``global`` section.

    Returns
    -------
    Global settings dict.
    """
    return load_config().get("global", {})
