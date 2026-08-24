"""Nautilus: overlay emblems + Make available offline / Free up space."""

from __future__ import annotations

import fnmatch
import json
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from gi import require_version

require_version("Nautilus", "4.1")

from gi.repository import Gio, GObject, Nautilus  # noqa: E402

def _ensure_omgee_on_path() -> None:
    candidates = [
        Path.home() / ".local" / "lib" / "omgee-drive",
        Path.home() / ".local" / "lib" / "omgee-drive" / "OMGee_Drive",
        Path.home() / "Projects" / "OMGee_Drive",
    ]
    for root in candidates:
        if (root / "omgee_drive" / "status.py").exists():
            resolved = str(root.resolve())
            if resolved not in sys.path:
                sys.path.insert(0, resolved)
            return


_ensure_omgee_on_path()

try:
    from omgee_drive.status import emblems_for, is_pinned_rel, is_stub as _is_stub
    from omgee_drive.status import is_ignored as _is_ignored
    from omgee_drive.status import label_for
except Exception:  # noqa: BLE001 — keep the menu working if imports fail
    emblems_for = None
    label_for = None
    _is_stub = None
    is_pinned_rel = None
    _is_ignored = None

STUB_SUFFIXES = {
    ".gdoc",
    ".gsheet",
    ".gslides",
    ".gform",
    ".gdraw",
    ".gjam",
    ".gsite",
    ".gshortcut",
    ".gmap",
    ".gscript",
}


_MOUNT: Path | None = None
_SNAP: dict = {"t": 0.0}


def _mount_point() -> Path:
    global _MOUNT
    if _MOUNT is not None:
        return _MOUNT
    conf = Path.home() / ".config" / "omgee-drive" / "config.json"
    mount = Path.home() / "GoogleDrive"
    if conf.exists():
        try:
            data = json.loads(conf.read_text(encoding="utf-8"))
            mount = Path(data.get("mount_point") or mount).expanduser()
        except json.JSONDecodeError:
            pass
    _MOUNT = mount
    return _MOUNT


def _rel(path: Path, mount: Path) -> str | None:
    # String prefix only — never Path.resolve() on the rclone FUSE mount.
    p = str(path)
    m = str(mount).rstrip("/")
    if p == m:
        return None
    prefix = m + "/"
    if p.startswith(prefix):
        return p[len(prefix) :]
    return None


def _stub(path: Path) -> bool:
    if _is_stub is not None:
        return _is_stub(path)
    return path.suffix.lower() in STUB_SUFFIXES


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
    "conflict": "Conflict",
    "paused": "Offline",
    "ignored": "Ignored",
}


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _covered(rel: str, items) -> bool:
    rel = (rel or "").strip("/")
    if not rel:
        return False
    bag = items if isinstance(items, set) else set(items)
    cur = rel
    while True:
        if cur in bag:
            return True
        if "/" not in cur:
            return False
        cur = cur.rsplit("/", 1)[0]


def _snapshot() -> dict:
    now = time.monotonic()
    if now - float(_SNAP.get("t") or 0) < 1.0 and "pins" in _SNAP:
        return _SNAP
    home = Path.home()
    pins = _read_json(home / ".local" / "share" / "omgee-drive" / "pins.json", {})
    data = _read_json(home / ".local" / "share" / "omgee-drive" / "status.json", {})
    patterns: list[str] = []
    ignore_file = home / ".config" / "omgee-drive" / "ignore"
    if ignore_file.exists():
        try:
            for line in ignore_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        except OSError:
            pass
    _SNAP.update(
        {
            "t": now,
            "pins": {str(p).strip("/") for p in pins.get("paths") or []},
            "syncing": set(data.get("syncing") or []),
            "errors": set(data.get("errors") or {}),
            "conflicts": set(data.get("conflicts") or {}),
            "ignored": set(data.get("ignored") or []),
            "shared": set(data.get("shared") or []),
            "offline": bool(data.get("offline")),
            "globs": patterns,
        }
    )
    return _SNAP


def _pins() -> set[str]:
    return _snapshot()["pins"]


def _status_blob() -> dict:
    snap = _snapshot()
    return {
        "syncing": snap["syncing"],
        "errors": {k: True for k in snap["errors"]},
        "conflicts": {k: True for k in snap["conflicts"]},
        "ignored": snap["ignored"],
        "shared": snap["shared"],
        "offline": snap["offline"],
    }


def _ignored(rel: str) -> bool:
    snap = _snapshot()
    if _covered(rel, snap["ignored"]):
        return True
    name = rel.split("/")[-1] if rel else ""
    for pat in snap.get("globs") or []:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
            return True
    return False


def _local_status(rel: str, path: Path) -> str:
    snap = _snapshot()
    if _ignored(rel):
        return "ignored"
    if _covered(rel, snap["errors"]):
        return "error"
    if _covered(rel, snap["conflicts"]):
        return "conflict"
    if _stub(path):
        return "paused" if snap["offline"] else "web"
    if _covered(rel, snap["syncing"]):
        return "paused" if snap["offline"] else "sync"
    if _covered(rel, snap["pins"]):
        return "ok"
    if snap["offline"]:
        return "paused"
    return "cloud"


def _emblems(rel: str, path: Path) -> list[str]:
    # Local snapshot only — do not call into omgee_drive on the FUSE hot path.
    key = _local_status(rel, path)
    names = [EMBLEMS[key]]
    if key not in ("ignored", "paused") and _covered(rel, _snapshot()["shared"]):
        names.append(EMBLEMS["shared"])
    return names


def _label(rel: str, path: Path) -> str:
    if label_for is not None:
        try:
            return label_for(rel, path)
        except Exception:
            pass
    return LABELS[_local_status(rel, path)]


def _pinned(rel: str) -> bool:
    if is_pinned_rel is not None:
        try:
            return is_pinned_rel(rel)
        except Exception:
            pass
    return _covered(rel, _pins())


class OmgeeDriveExtension(
    GObject.GObject, Nautilus.MenuProvider, Nautilus.InfoProvider, Nautilus.ColumnProvider
):
    def _omgee(self) -> str | None:
        found = shutil.which("omgee-drive")
        if found:
            return found
        fallback = Path.home() / ".local" / "bin" / "omgee-drive"
        return str(fallback) if fallback.exists() else None

    def _selected(self, files):
        mount = _mount_point()
        paths = []
        for file in files:
            uri = file.get_uri() or ""
            if not uri.startswith("file:"):
                continue
            raw = unquote(urlparse(uri).path)
            if not raw:
                continue
            p = Path(raw)
            if _rel(p, mount) is None:
                continue
            paths.append((file, p))
        return paths

    def _run(self, subcmd: str, files_and_paths):
        binary = self._omgee()
        if not binary:
            return
        files = [pair[0] for pair in files_and_paths]
        paths = [str(pair[1]) for pair in files_and_paths]
        proc = Gio.Subprocess.new(
            [binary, subcmd, "--notify", *paths],
            Gio.SubprocessFlags.NONE,
        )

        def _done(subprocess, result):
            try:
                subprocess.wait_finish(result)
            except Exception:
                pass
            for file in files:
                try:
                    file.invalidate_extension_info()
                except Exception:
                    pass

        proc.wait_async(None, _done)

    def get_columns(self):
        return [
            Nautilus.Column(
                name="OmgeeDrive::status",
                attribute="omgee_status",
                label="Drive",
                description="OMGee Drive status",
            )
        ]

    def update_file_info(self, file, *args):
        uri = file.get_uri() or ""
        if not uri.startswith("file:"):
            return Nautilus.OperationResult.COMPLETE
        raw = unquote(urlparse(uri).path)
        if not raw:
            return Nautilus.OperationResult.COMPLETE
        path = Path(raw)
        rel = _rel(path, _mount_point())
        if rel is None:
            return Nautilus.OperationResult.COMPLETE
        try:
            for name in _emblems(rel, path):
                file.add_emblem(name)
            file.add_string_attribute("omgee_status", _label(rel, path))
        except Exception:
            return Nautilus.OperationResult.FAILED
        return Nautilus.OperationResult.COMPLETE

    def get_file_items(self, *args):
        files = args[0] if len(args) == 1 else args[1]
        if not self._omgee():
            return []
        selected = self._selected(files)
        if not selected:
            return []

        stubs = [pair for pair in selected if _stub(pair[1])]
        rest = [pair for pair in selected if pair not in stubs]
        children = []
        icon = "omgee-drive"

        pinned = []
        unpinned = []
        ignored = []
        watchable = []
        for pair in rest:
            rel = _rel(pair[1], _mount_point())
            if rel is None:
                continue
            if _ignored(rel):
                ignored.append(pair)
                continue
            watchable.append(pair)
            if _pinned(rel):
                pinned.append(pair)
            else:
                unpinned.append(pair)

        if unpinned:
            item = Nautilus.MenuItem(
                name="OmgeeDrive::pin",
                label="Make available offline"
                if len(unpinned) == 1
                else f"Make {len(unpinned)} items available offline",
                icon=icon,
            )
            item.connect("activate", self._on_pin, unpinned)
            children.append(item)

        if pinned:
            item = Nautilus.MenuItem(
                name="OmgeeDrive::unpin",
                label="Free up space"
                if len(pinned) == 1
                else f"Free space for {len(pinned)} items",
                icon=icon,
            )
            item.connect("activate", self._on_unpin, pinned)
            children.append(item)

        if watchable:
            item = Nautilus.MenuItem(
                name="OmgeeDrive::ignore",
                label="Ignore"
                if len(watchable) == 1
                else f"Ignore {len(watchable)} items",
                icon=icon,
            )
            item.connect("activate", self._on_ignore, watchable)
            children.append(item)

        if ignored:
            item = Nautilus.MenuItem(
                name="OmgeeDrive::unignore",
                label="Stop ignoring"
                if len(ignored) == 1
                else f"Stop ignoring {len(ignored)} items",
                icon=icon,
            )
            item.connect("activate", self._on_unignore, ignored)
            children.append(item)

        if stubs:
            item = Nautilus.MenuItem(
                name="OmgeeDrive::open",
                label="Open in browser"
                if len(stubs) == 1
                else f"Open {len(stubs)} shortcuts in browser",
                icon=icon,
            )
            item.connect("activate", self._on_open, stubs)
            children.append(item)

        if not children:
            return []

        submenu = Nautilus.Menu()
        for child in children:
            submenu.append_item(child)
        parent = Nautilus.MenuItem(
            name="OmgeeDrive::root",
            label="OMGee Drive",
            icon=icon,
        )
        parent.set_submenu(submenu)
        return [parent]

    def _on_pin(self, _menu, pairs):
        self._run("pin", pairs)

    def _on_unpin(self, _menu, pairs):
        self._run("unpin", pairs)

    def _on_ignore(self, _menu, pairs):
        self._run("ignore", pairs)

    def _on_unignore(self, _menu, pairs):
        self._run("unignore", pairs)

    def _on_open(self, _menu, pairs):
        binary = self._omgee()
        if not binary:
            return
        for _file, path in pairs:
            Gio.Subprocess.new(
                [binary, "open", str(path)], Gio.SubprocessFlags.NONE
            )
