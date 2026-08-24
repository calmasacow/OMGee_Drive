from __future__ import annotations

from pathlib import Path

APP_NAME = "omgee-drive"

CONFIG_DIR = Path.home() / ".config" / APP_NAME
DATA_DIR = Path.home() / ".local" / "share" / APP_NAME
CACHE_DIR = Path.home() / ".cache" / APP_NAME
LOCAL_DIR = DATA_DIR / "local"

CONFIG_FILE = CONFIG_DIR / "config.json"
RCLONE_CONF = CONFIG_DIR / "rclone.conf"
PINS_FILE = DATA_DIR / "pins.json"
STATUS_FILE = DATA_DIR / "status.json"

DEFAULT_MOUNT = Path.home() / "GoogleDrive"

REMOTE_DRIVE = "omgee-gdrive"
REMOTE_LOCAL = "omgee-local"
REMOTE_UNION = "omgee"

STUB_MIME = {
    "application/vnd.google-apps.document": "gdoc",
    "application/vnd.google-apps.spreadsheet": "gsheet",
    "application/vnd.google-apps.presentation": "gslides",
    "application/vnd.google-apps.form": "gform",
    "application/vnd.google-apps.drawing": "gdraw",
    "application/vnd.google-apps.jam": "gjam",
    "application/vnd.google-apps.site": "gsite",
    "application/vnd.google-apps.shortcut": "gshortcut",
    "application/vnd.google-apps.map": "gmap",
    "application/vnd.google-apps.script": "gscript",
}

STUB_SUFFIXES = {f".{ext}" for ext in STUB_MIME.values()}

STUB_EXCLUDE_GLOBS = [f"*.{ext}" for ext in STUB_MIME.values()]


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
