from __future__ import annotations

import json
from pathlib import Path

from omgee_drive.paths import (
    PINS_FILE,
    STATUS_FILE,
    STUB_SUFFIXES,
    ensure_dirs,
)

# Nautilus emblem names (files in icons/emblem-omgee-*.svg).
EMBLEMS = {
    "ok": "emblem-omgee-ok",
    "sync": "emblem-omgee-sync",
    "cloud": "emblem-omgee-cloud",
    "error": "emblem-omgee-error",
    "web": "emblem-omgee-web",
}

LABELS = {
    "ok": "Available offline",
    "sync": "Syncing",
    "cloud": "Online only",
    "error": "Sync error",
    "web": "Opens in browser",
}

_EMPTY = {"syncing": [], "errors": {}}
_cache = {
    "pins_mtime": None,
    "status_mtime": None,
    "pins": set(),
    "status": {"syncing": [], "errors": {}},
}


def _read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _mtime(path: Path):
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def load() -> dict:
    mtime = _mtime(STATUS_FILE)
    if mtime == _cache["status_mtime"]:
        data = _cache["status"]
        return {"syncing": list(data["syncing"]), "errors": dict(data["errors"])}
    data = _read_json(STATUS_FILE, {})
    parsed = {
        "syncing": list(data.get("syncing") or []),
        "errors": dict(data.get("errors") or {}),
    }
    _cache["status"] = parsed
    _cache["status_mtime"] = mtime
    return {"syncing": list(parsed["syncing"]), "errors": dict(parsed["errors"])}


def save(data: dict) -> None:
    ensure_dirs()
    payload = {
        "syncing": sorted(set(data.get("syncing") or [])),
        "errors": dict(data.get("errors") or {}),
    }
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATUS_FILE)
    _cache["status"] = {
        "syncing": list(payload["syncing"]),
        "errors": dict(payload["errors"]),
    }
    _cache["status_mtime"] = _mtime(STATUS_FILE)


def load_pins() -> set[str]:
    mtime = _mtime(PINS_FILE)
    if mtime == _cache["pins_mtime"]:
        return set(_cache["pins"])
    data = _read_json(PINS_FILE, {})
    pins = {str(p).strip("/") for p in data.get("paths") or []}
    _cache["pins"] = pins
    _cache["pins_mtime"] = mtime
    return set(pins)


def is_stub(path: Path) -> bool:
    return path.suffix.lower() in STUB_SUFFIXES


def is_pinned_rel(rel: str) -> bool:
    return _covered(rel, load_pins())


def _covered(rel: str, items: list[str] | set[str]) -> bool:
    rel = rel.strip("/")
    bag = set(items)
    if rel in bag:
        return True
    parts = rel.split("/")
    for i in range(1, len(parts)):
        if "/".join(parts[:i]) in bag:
            return True
    return False


def mark_syncing(rel: str) -> None:
    rel = rel.strip("/")
    data = load()
    if rel not in data["syncing"]:
        data["syncing"].append(rel)
    data["errors"].pop(rel, None)
    save(data)


def mark_ok(rel: str) -> None:
    rel = rel.strip("/")
    data = load()
    data["syncing"] = [p for p in data["syncing"] if p != rel]
    data["errors"].pop(rel, None)
    save(data)


def mark_error(rel: str, message: str) -> None:
    rel = rel.strip("/")
    data = load()
    data["syncing"] = [p for p in data["syncing"] if p != rel]
    data["errors"][rel] = message[:400]
    save(data)


def clear_rel(rel: str) -> None:
    rel = rel.strip("/")
    data = load()
    data["syncing"] = [p for p in data["syncing"] if p != rel]
    data["errors"].pop(rel, None)
    save(data)


def status_for(rel: str, path: Path | None = None) -> str:
    """Return ok | sync | cloud | error | web."""
    rel = (rel or "").strip("/")
    if path is not None and is_stub(path):
        return "web"
    data = load()
    if _covered(rel, data["errors"].keys()) or rel in data["errors"]:
        return "error"
    if _covered(rel, data["syncing"]):
        return "sync"
    if _covered(rel, load_pins()):
        return "ok"
    return "cloud"


def emblem_for(rel: str, path: Path | None = None) -> str:
    return EMBLEMS[status_for(rel, path)]


def label_for(rel: str, path: Path | None = None) -> str:
    key = status_for(rel, path)
    if key == "error":
        msg = load()["errors"].get(rel) or "Sync error"
        return msg
    return LABELS[key]
