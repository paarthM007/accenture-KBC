"""Loads metric_config.yaml into a plain dict, cached for the process lifetime."""

from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent / "metric_config.yaml"


@lru_cache(maxsize=1)
def load_metric_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def metrics() -> dict:
    return load_metric_config()["metrics"]


def thresholds() -> dict:
    return load_metric_config()["thresholds"]


def revenue_bands() -> list[dict]:
    return load_metric_config()["revenue_bands"]
