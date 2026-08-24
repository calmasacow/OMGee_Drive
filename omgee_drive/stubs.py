from __future__ import annotations

import json
from pathlib import Path

from omgee_drive import rclone
from omgee_drive import status as st
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


def _item_shared(item: dict) -> bool:
    md = item.get("Metadata") or {}
    if str(md.get("shared", "")).lower() == "true":
        return True
    raw = md.get("permissions")
    if not raw:
        return False
    try:
        perms = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return False
    if not isinstance(perms, list):
        return False
    extras = [
        p
        for p in perms
        if isinstance(p, dict) and p.get("role") not in (None, "owner")
    ]
    return len(perms) > 1 or bool(extras)


def refresh(*, with_sharing: bool = False) -> tuple[int, int]:
    """Create/update stubs. Sharing metadata is an optional extra Drive API pass."""
    ensure_dirs()
    try:
        extra = ["--drive-skip-gdocs=false", "--drive-show-all-gdocs"]
        if with_sharing:
            extra += ["--metadata", "--drive-metadata-permissions=read"]
        items = rclone.lsjson(f"{REMOTE_DRIVE}:", extra=extra)
        st.set_offline(False)
    except rclone.RcloneError:
        st.set_offline(True)
        return 0, 0

    keep: set[str] = set()
    written = 0
    shared: list[str] = []
    for item in items:
        path = (item.get("Path") or "").strip("/")
        stub = stub_relpath(item)
        catalog = stub or path
        if with_sharing and catalog and _item_shared(item):
            shared.append(catalog)
        mime = item.get("MimeType") or ""
        if not mime.startswith("application/vnd.google-apps."):
            continue
        if mime == "application/vnd.google-apps.folder":
            continue
        dest = write_stub(item)
        if dest:
            keep.add(str(dest.relative_to(LOCAL_DIR)))
            written += 1

    if with_sharing:
        st.set_shared(shared)

    removed = 0
    if LOCAL_DIR.exists():
        for path in LOCAL_DIR.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in STUB_SUFFIXES:
                continue
            rel = str(path.relative_to(LOCAL_DIR))
            if rel not in keep:
                path.unlink()
                removed += 1
    return written, removed
