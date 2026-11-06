import json
import sys
from pathlib import Path

from adapters.css_source import CssSource
from adapters.shaonian import ShaonianSource


def load_sources():
    bundled_path = Path(__file__).with_name("sources.json")
    config_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else bundled_path.parent
    path = config_dir / "sources.local.json"
    if not path.is_file():
        path = config_dir / "sources.json"
    if not path.is_file():
        path = bundled_path
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    adapters = {"shaonian": ShaonianSource, "css": CssSource}
    return [
        adapters[entry["adapter"]](entry["rule"])
        for group in config["sets"].values()
        for entry in group
        if entry["enabled"] and entry["adapter"] in adapters
    ]
