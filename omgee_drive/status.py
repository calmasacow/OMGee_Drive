from __future__ import annotations

import fnmatch
import json
from pathlib import Path

from omgee_drive.paths import (
    IGNORE_FILE,
    PINS_FILE,
    STATUS_FILE,
    STUB_SUFFIXES,
    SYNC_INDEX_FILE,
    ensure_dirs,
)

# Nautilus emblem names (files in icons/emblem-omgee-*.svg).
EMBLEMS = {
    "ok": "emblem-omgee-ok",
    "sync": "emblem-omgee-sync",
    "cloud": "emblem-omgee-cloud",
    "error": "emblem-omgee-error",
    "web": "emblem-omgee-web",
    "conflict": "emblem-omgee-conflict",
    "paused": "emblem-omgee-paused",
    "shared": "emblem-omgee-shared",
    "ignored": "emblem-omgee-ignored",
}

LABELS = {
    "ok": "Available offline",
    "sync": "Syncing",
    "cloud": "Online only",
    "error": "Sync error",
    "web": "Opens in browser",
    "conflict": "Conflict — local and Drive both changed",
    "paused": "Offline — Drive unreachable",
    "shared": "Shared",
    "ignored": "Ignored",
}

_DEFAULT = {
    "syncing": [],
    "errors": {},
    "conflicts": {},
    "ignored": [],
    "shared": [],
    "offline": False,
}
_cache = {
    "pins_mtime": None,
    "status_mtime": None,
    "ignore_mtime": None,
    "pins": set(),
    "status": dict(_DEFAULT),
    "ignore_patterns": [],
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


def _normalize(data: dict) -> dict:
    return {
        "syncing": list(data.get("syncing") or []),
        "errors": dict(data.get("errors") or {}),
        "conflicts": dict(data.get("conflicts") or {}),
        "ignored": list(data.get("ignored") or []),
        "shared": list(data.get("shared") or []),
        "offline": bool(data.get("offline")),
    }


def load() -> dict:
    mtime = _mtime(STATUS_FILE)
    if mtime == _cache["status_mtime"]:
        return _normalize(_cache["status"])
    parsed = _normalize(_read_json(STATUS_FILE, {}))
    _cache["status"] = parsed
    _cache["status_mtime"] = mtime
    return _normalize(parsed)


def save(data: dict) -> None:
    ensure_dirs()
    payload = _normalize(data)
    payload["syncing"] = sorted(set(payload["syncing"]))
    payload["ignored"] = sorted(set(payload["ignored"]))
    payload["shared"] = sorted(set(payload["shared"]))
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATUS_FILE)
    _cache["status"] = _normalize(payload)
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


def ignore_patterns() -> list[str]:
    mtime = _mtime(IGNORE_FILE)
    if mtime == _cache["ignore_mtime"] and _cache["ignore_patterns"] is not None:
        return list(_cache["ignore_patterns"])
    patterns: list[str] = []
    if IGNORE_FILE.exists():
        for line in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    _cache["ignore_patterns"] = patterns
    _cache["ignore_mtime"] = mtime
    return list(patterns)


def is_stub(path: Path) -> bool:
    return path.suffix.lower() in STUB_SUFFIXES


def is_pinned_rel(rel: str) -> bool:
    return _covered(rel, load_pins())


def _covered(rel: str, items: list[str] | set[str]) -> bool:
    rel = (rel or "").strip("/")
    bag = {str(x).strip("/") for x in items}
    if rel in bag:
        return True
    parts = rel.split("/")
    for i in range(1, len(parts)):
        if "/".join(parts[:i]) in bag:
            return True
    return False


def is_ignored(rel: str) -> bool:
    rel = (rel or "").strip("/")
    data = load()
    if _covered(rel, data["ignored"]):
        return True
    name = rel.split("/")[-1] if rel else ""
    for pat in ignore_patterns():
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
            return True
    return False


def is_shared(rel: str) -> bool:
    return _covered(rel, load()["shared"])


def mark_syncing(rel: str) -> None:
    rel = rel.strip("/")
    data = load()
    if rel not in data["syncing"]:
        data["syncing"].append(rel)
    data["errors"].pop(rel, None)
    data["conflicts"].pop(rel, None)
    save(data)


def mark_ok(rel: str) -> None:
    rel = rel.strip("/")
    data = load()
    data["syncing"] = [p for p in data["syncing"] if p != rel]
    data["errors"].pop(rel, None)
    data["conflicts"].pop(rel, None)
    save(data)


def mark_error(rel: str, message: str) -> None:
    rel = rel.strip("/")
    data = load()
    data["syncing"] = [p for p in data["syncing"] if p != rel]
    data["errors"][rel] = message[:400]
    save(data)


def mark_conflict(rel: str, message: str = "") -> None:
    rel = rel.strip("/")
    data = load()
    data["syncing"] = [p for p in data["syncing"] if p != rel]
    data["conflicts"][rel] = (message or "Local and Drive both changed")[:400]
    save(data)


def set_offline(offline: bool) -> None:
    data = load()
    if bool(data["offline"]) == bool(offline):
        return
    data["offline"] = bool(offline)
    save(data)


def set_shared(paths: list[str]) -> None:
    data = load()
    data["shared"] = sorted({p.strip("/") for p in paths if p})
    save(data)


def ignore(rel: str) -> None:
    rel = rel.strip("/")
    data = load()
    if rel not in data["ignored"]:
        data["ignored"].append(rel)
    save(data)


def unignore(rel: str) -> None:
    rel = rel.strip("/")
    data = load()
    data["ignored"] = [p for p in data["ignored"] if p != rel]
    save(data)


def clear_rel(rel: str) -> None:
    rel = rel.strip("/")
    data = load()
    data["syncing"] = [p for p in data["syncing"] if p != rel]
    data["errors"].pop(rel, None)
    data["conflicts"].pop(rel, None)
    save(data)


def status_for(rel: str, path: Path | None = None) -> str:
    """Primary badge: ignored | error | conflict | paused | sync | web | ok | cloud."""
    rel = (rel or "").strip("/")
    if is_ignored(rel):
        return "ignored"
    data = load()
    if rel in data["errors"] or _covered(rel, data["errors"].keys()):
        return "error"
    if rel in data["conflicts"] or _covered(rel, data["conflicts"].keys()):
        return "conflict"
    if path is not None and is_stub(path):
        if data["offline"]:
            return "paused"
        return "web"
    if _covered(rel, data["syncing"]):
        return "paused" if data["offline"] else "sync"
    if _covered(rel, load_pins()):
        return "ok"
    if data["offline"]:
        return "paused"
    return "cloud"


def emblems_for(rel: str, path: Path | None = None) -> list[str]:
    primary = status_for(rel, path)
    names = [EMBLEMS[primary]]
    if primary not in ("ignored", "paused") and is_shared(rel):
        names.append(EMBLEMS["shared"])
    return names


def emblem_for(rel: str, path: Path | None = None) -> str:
    return emblems_for(rel, path)[0]


def label_for(rel: str, path: Path | None = None) -> str:
    key = status_for(rel, path)
    data = load()
    if key == "error":
        return data["errors"].get(rel) or LABELS["error"]
    if key == "conflict":
        return data["conflicts"].get(rel) or LABELS["conflict"]
    label = LABELS[key]
    if is_shared(rel) and key not in ("ignored", "paused"):
        return f"{label} · shared"
    return label


def load_sync_index() -> dict:
    return dict(_read_json(SYNC_INDEX_FILE, {}))


def save_sync_index(index: dict) -> None:
    ensure_dirs()
    tmp = SYNC_INDEX_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    tmp.replace(SYNC_INDEX_FILE)


def record_sync(rel: str, local_mtime: int | None, remote_mtime: str | None) -> None:
    rel = rel.strip("/")
    index = load_sync_index()
    index[rel] = {"local_mtime": local_mtime, "remote_mtime": remote_mtime}
    save_sync_index(index)


def drop_sync_record(rel: str) -> None:
    rel = rel.strip("/")
    index = load_sync_index()
    if rel in index:
        del index[rel]
        save_sync_index(index)
