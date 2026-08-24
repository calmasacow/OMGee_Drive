from __future__ import annotations

import json
from pathlib import Path

from omgee_drive.paths import CONFIG_FILE, DEFAULT_MOUNT, ensure_dirs


DEFAULTS = {
    "mount_point": str(DEFAULT_MOUNT),
    "stub_refresh_sec": 300,
    "pin_sync_sec": 300,
}


def load() -> dict:
    ensure_dirs()
    if not CONFIG_FILE.exists():
        save(DEFAULTS.copy())
        return DEFAULTS.copy()
    data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    merged = DEFAULTS.copy()
    merged.update(data)
    return merged


def save(data: dict) -> None:
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def mount_point() -> Path:
    return Path(load()["mount_point"]).expanduser()
