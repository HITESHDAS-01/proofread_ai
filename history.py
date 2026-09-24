import json
import time
from datetime import datetime

from config import get, history_file


def _load() -> list:
    path = history_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def add(original: str, corrected: str, provider: str = "") -> dict:
    entry = {
        "ts": time.time(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "original": original,
        "corrected": corrected,
        "provider": provider,
    }
    items = _load()
    items.insert(0, entry)
    limit = int(get("max_history", 100) or 100)
    items = items[: max(1, limit)]
    try:
        history_file().write_text(
            json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass
    return entry


def list_items() -> list:
    return _load()


def clear() -> None:
    try:
        history_file().write_text("[]", encoding="utf-8")
    except OSError:
        pass
