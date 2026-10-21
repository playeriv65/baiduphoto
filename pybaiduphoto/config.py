"""Load non-secret defaults and optional local overrides."""

import json
import os
from pathlib import Path


def load_config(path=None):
    config = json.loads(Path(__file__).with_name("defaults.json").read_text("utf-8"))
    path = path or os.environ.get("BAIDUPHOTO_CONFIG")
    if path:
        config.update(json.loads(Path(path).read_text("utf-8")))
    if float(config["timeout_seconds"]) <= 0:
        raise ValueError("timeout_seconds must be positive")
    if float(config["page_delay_seconds"]) < 0:
        raise ValueError("page_delay_seconds must be non-negative")
    if not isinstance(config["page_size"], int) or not 1 <= config["page_size"] <= 100:
        raise ValueError("page_size must be an integer between 1 and 100")
    return config
