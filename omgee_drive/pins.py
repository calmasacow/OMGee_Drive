from __future__ import annotations

import json
from pathlib import Path

from omgee_drive import rclone
from omgee_drive import status as st
from omgee_drive.paths import (
    LOCAL_DIR,
    PINS_FILE,
    REMOTE_DRIVE,
    REMOTE_LOCAL,
    STUB_EXCLUDE_GLOBS,
    STUB_SUFFIXES,
    ensure_dirs,
)
from omgee_drive.config import mount_point


def load_pins() -> list[str]:
    if not PINS_FILE.exists():
        return []
    data = json.loads(PINS_FILE.read_text(encoding="utf-8"))
    return list(data.get("paths", []))


def save_pins(paths: list[str]) -> None:
    ensure_dirs()
    unique = sorted(set(paths))
    PINS_FILE.write_text(
        json.dumps({"paths": unique}, indent=2) + "\n", encoding="utf-8"
    )


def rel_from_user_path(path: Path) -> str:
    mount = mount_point().resolve()
    resolved = path.expanduser().resolve()
    try:
        rel = resolved.relative_to(mount)
    except ValueError:
        # Might be a path already relative, or under the local overlay.
        try:
            rel = resolved.relative_to(LOCAL_DIR.resolve())
        except ValueError as exc:
            raise ValueError(
                f"{path} is not inside {mount}. Open Nautilus on your GoogleDrive folder."
            ) from exc
    return str(rel).replace("\\", "/")


def is_stub(path: Path) -> bool:
    return path.suffix.lower() in STUB_SUFFIXES


def is_pinned(rel: str) -> bool:
    rel = rel.strip("/")
    pins = load_pins()
    if rel in pins:
        return True
    parts = rel.split("/")
    for i in range(1, len(parts)):
        parent = "/".join(parts[:i])
        if parent in pins:
            return True
    return False


def local_path(rel: str) -> Path:
    return LOCAL_DIR / rel


def pin(paths: list[Path]) -> list[str]:
    ensure_dirs()
    pins = load_pins()
    jobs: list[tuple[str, Path]] = []
    for path in paths:
        rel = rel_from_user_path(path)
        if is_stub(path) or is_stub(local_path(rel)):
            continue
        if st.is_ignored(rel):
            continue
        jobs.append((rel, path))
        if rel not in pins:
            pins.append(rel)
        st.mark_syncing(rel)
    save_pins(pins)
    added: list[str] = []
    for rel, path in jobs:
        try:
            _hydrate(rel, path)
        except Exception as exc:  # noqa: BLE001 — surface per-file, keep going
            st.mark_error(rel, str(exc))
            continue
        st.mark_ok(rel)
        _record(rel, local_path(rel))
        added.append(rel)
    return added


def unpin(paths: list[Path]) -> list[str]:
    pins = load_pins()
    removed: list[str] = []
    remaining = list(pins)
    for path in paths:
        rel = rel_from_user_path(path)
        if rel in remaining:
            remaining.remove(rel)
            removed.append(rel)
        target = local_path(rel)
        if target.exists() and not is_stub(target):
            if target.is_dir():
                _rmtree_keep_stubs(target)
            else:
                target.unlink()
        st.clear_rel(rel)
        st.drop_sync_record(rel)
    save_pins(remaining)
    return removed


def _hydrate(rel: str, original: Path) -> None:
    dest = local_path(rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = f"{REMOTE_DRIVE}:{rel}"
    if original.is_dir() or dest.is_dir():
        rclone.copy_tree(src, f"{REMOTE_LOCAL}:{rel}")
    else:
        rclone.copyto(src, f"{REMOTE_LOCAL}:{rel}")


def _rmtree_keep_stubs(root: Path) -> None:
    if not root.exists():
        return
    for child in sorted(root.rglob("*"), reverse=True):
        if child.is_file() and not is_stub(child):
            child.unlink()
        elif child.is_dir() and not any(child.iterdir()):
            child.rmdir()
    if root.is_dir() and not any(root.iterdir()):
        root.rmdir()


def _record(rel: str, local: Path) -> None:
    remote = rclone.stat(f"{REMOTE_DRIVE}:{rel}")
    local_mtime = None
    if local.exists() and local.is_file():
        local_mtime = local.stat().st_mtime_ns
    st.record_sync(rel, local_mtime, (remote or {}).get("ModTime"))


def _has_conflict(rel: str, local: Path) -> bool:
    if not local.is_file():
        return False
    saved = st.load_sync_index().get(rel) or {}
    if not saved:
        return False
    remote = rclone.stat(f"{REMOTE_DRIVE}:{rel}")
    remote_now = (remote or {}).get("ModTime")
    local_now = local.stat().st_mtime_ns
    local_changed = (
        saved.get("local_mtime") is not None and local_now != saved.get("local_mtime")
    )
    remote_changed = bool(
        saved.get("remote_mtime") and remote_now and remote_now != saved.get("remote_mtime")
    )
    return bool(local_changed and remote_changed)


def sync_pins() -> None:
    """Keep pinned files in both directions. Stubs never upload."""
    excludes = []
    for glob in STUB_EXCLUDE_GLOBS:
        excludes.extend(["--exclude", glob])
    for rel in load_pins():
        if st.is_ignored(rel):
            continue
        src = f"{REMOTE_DRIVE}:{rel}"
        dest = f"{REMOTE_LOCAL}:{rel}"
        local = local_path(rel)
        try:
            if _has_conflict(rel, local):
                st.mark_conflict(rel)
                continue
            if local.is_dir() or not local.exists():
                rclone.copy_tree(src, dest, extra=["--update"])
                rclone.copy_tree(dest, src, extra=["--update", *excludes])
            else:
                rclone.run(["copyto", src, dest, "--update"], check=True)
                rclone.run(["copyto", dest, src, "--update"], check=True)
            st.mark_ok(rel)
            _record(rel, local)
        except rclone.RcloneError as exc:
            msg = str(exc).lower()
            if any(
                token in msg
                for token in (
                    "couldn't connect",
                    "network is unreachable",
                    "i/o timeout",
                    "temporary failure",
                    "no route to host",
                    "connection refused",
                )
            ):
                st.set_offline(True)
            continue
