"""Loading of the per-city YAML configuration."""

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
MANUAL_DIR = DATA_DIR / "manual"


def load_config(city: str = "bari") -> dict[str, Any]:
    path = CONFIG_DIR / f"{city}.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def project_path(relative: str) -> Path:
    """Resolve a path from the config (relative to the project root)."""
    return PROJECT_ROOT / relative
