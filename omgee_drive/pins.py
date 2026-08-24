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


def sync_pins() -> None:
    """Keep pinned files in both directions. Stubs never upload."""
    excludes = []
    for glob in STUB_EXCLUDE_GLOBS:
        excludes.extend(["--exclude", glob])
    for rel in load_pins():
        src = f"{REMOTE_DRIVE}:{rel}"
        dest = f"{REMOTE_LOCAL}:{rel}"
        local = local_path(rel)
        try:
            if local.is_dir() or not local.exists():
                rclone.copy_tree(src, dest, extra=["--update"])
                rclone.copy_tree(dest, src, extra=["--update", *excludes])
            else:
                rclone.run(["copyto", src, dest, "--update"], check=True)
                rclone.run(["copyto", dest, src, "--update"], check=True)
        except rclone.RcloneError:
            # Offline or path vanished — leave the local pin alone.
            continue
