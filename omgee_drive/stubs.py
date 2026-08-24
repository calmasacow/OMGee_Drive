from __future__ import annotations

import json
from pathlib import Path

from omgee_drive import rclone
from omgee_drive.paths import LOCAL_DIR, REMOTE_DRIVE, STUB_MIME, STUB_SUFFIXES, ensure_dirs

STUB_MARKER = "omgee"


def _url_for(file_id: str) -> str:
    return f"https://drive.google.com/open?id={file_id}"


def stub_relpath(item: dict) -> str | None:
    mime = item.get("MimeType") or ""
    ext = STUB_MIME.get(mime)
    if not ext:
        return None
    path = (item.get("Path") or item.get("Name") or "").strip("/")
    if not path:
        return None
    parent, _, name = path.rpartition("/")
    stem = Path(name).stem or name
    filename = f"{stem}.{ext}"
    return f"{parent}/{filename}" if parent else filename


def write_stub(item: dict) -> Path | None:
    rel = stub_relpath(item)
    if not rel:
        return None
    dest = LOCAL_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        STUB_MARKER: 1,
        "id": item.get("ID"),
        "name": item.get("Name"),
        "mime": item.get("MimeType"),
        "url": _url_for(item.get("ID") or ""),
    }
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def read_stub(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or STUB_MARKER not in data:
        return None
    return data


def refresh() -> tuple[int, int]:
    """Create/update stubs for Google editor files. Returns (written, removed)."""
    ensure_dirs()
    items = rclone.lsjson(
        f"{REMOTE_DRIVE}:",
        extra=["--drive-skip-gdocs=false", "--drive-show-all-gdocs"],
    )
    keep: set[Path] = set()
    written = 0
    for item in items:
        if not (item.get("MimeType") or "").startswith("application/vnd.google-apps."):
            continue
        if item.get("MimeType") == "application/vnd.google-apps.folder":
            continue
        dest = write_stub(item)
        if dest:
            keep.add(dest.resolve())
            written += 1

    removed = 0
    if LOCAL_DIR.exists():
        for path in LOCAL_DIR.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in STUB_SUFFIXES:
                continue
            if path.resolve() not in keep:
                path.unlink()
                removed += 1
    return written, removed
