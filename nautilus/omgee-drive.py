"""Nautilus: overlay emblems + Make available offline / Free up space."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

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


def _mount_point() -> Path:
    conf = Path.home() / ".config" / "omgee-drive" / "config.json"
    if conf.exists():
        try:
            data = json.loads(conf.read_text(encoding="utf-8"))
            return Path(data.get("mount_point") or Path.home() / "GoogleDrive").expanduser()
        except json.JSONDecodeError:
            pass
    return Path.home() / "GoogleDrive"


def _rel(path: Path, mount: Path) -> str | None:
    try:
        rel = path.relative_to(mount)
    except ValueError:
        try:
            rel = path.resolve().relative_to(mount.resolve())
        except ValueError:
            return None
    text = str(rel).replace("\\", "/")
    if text in (".", ""):
        return None
    return text


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
    bag = {str(x).strip("/") for x in items}
    if rel in bag:
        return True
    parts = rel.split("/")
    for i in range(1, len(parts)):
        if "/".join(parts[:i]) in bag:
            return True
    return False


def _pins() -> set[str]:
    data = _read_json(Path.home() / ".local" / "share" / "omgee-drive" / "pins.json", {})
    return {str(p).strip("/") for p in data.get("paths") or []}


def _status_blob() -> dict:
    data = _read_json(Path.home() / ".local" / "share" / "omgee-drive" / "status.json", {})
    return {
        "syncing": list(data.get("syncing") or []),
        "errors": dict(data.get("errors") or {}),
        "conflicts": dict(data.get("conflicts") or {}),
        "ignored": list(data.get("ignored") or []),
        "shared": list(data.get("shared") or []),
        "offline": bool(data.get("offline")),
    }


def _ignored(rel: str) -> bool:
    if _is_ignored is not None:
        try:
            return _is_ignored(rel)
        except Exception:
            pass
    return _covered(rel, _status_blob()["ignored"])


def _local_status(rel: str, path: Path) -> str:
    blob = _status_blob()
    if _ignored(rel):
        return "ignored"
    if rel in blob["errors"] or _covered(rel, blob["errors"].keys()):
        return "error"
    if rel in blob["conflicts"] or _covered(rel, blob["conflicts"].keys()):
        return "conflict"
    if _stub(path):
        return "paused" if blob["offline"] else "web"
    if _covered(rel, blob["syncing"]):
        return "paused" if blob["offline"] else "sync"
    if _covered(rel, _pins()):
        return "ok"
    if blob["offline"]:
        return "paused"
    return "cloud"


def _emblems(rel: str, path: Path) -> list[str]:
    if emblems_for is not None:
        try:
            return emblems_for(rel, path)
        except Exception:
            pass
    names = [EMBLEMS[_local_status(rel, path)]]
    blob = _status_blob()
    if _local_status(rel, path) not in ("ignored", "paused") and _covered(
        rel, blob["shared"]
    ):
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
            location = file.get_location()
            if not location:
                continue
            raw = location.get_path()
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
        location = file.get_location()
        if not location:
            return Nautilus.OperationResult.COMPLETE
        raw = location.get_path()
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
