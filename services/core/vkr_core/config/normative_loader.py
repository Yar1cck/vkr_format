from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from services.core.vkr_core.config.settings import get_settings


def load_default_rules() -> dict[str, Any]:
    settings = get_settings()
    path = Path(settings.rules_file_path)
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
