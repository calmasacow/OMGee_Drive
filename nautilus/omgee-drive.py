"""Nautilus: overlay emblems + Make available offline / Free up space."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from gi import require_version

require_version("Nautilus", "4.1")

from gi.repository import Gio, GObject, Nautilus  # noqa: E402

_LIB = Path.home() / ".local" / "lib" / "omgee-drive"
if _LIB.exists() and str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

try:
    from omgee_drive.status import emblem_for, is_pinned_rel, is_stub as _is_stub
    from omgee_drive.status import label_for
except Exception:  # noqa: BLE001 — keep the menu working if imports fail
    emblem_for = None
    label_for = None
    _is_stub = None
    is_pinned_rel = None

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


def _pinned(rel: str) -> bool:
    if is_pinned_rel is None:
        return False
    return is_pinned_rel(rel)


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

    def update_file_info(self, file):
        if emblem_for is None:
            return
        location = file.get_location()
        if not location:
            return
        raw = location.get_path()
        if not raw:
            return
        mount = _mount_point()
        path = Path(raw)
        rel = _rel(path, mount)
        if rel is None:
            return
        try:
            emblem = emblem_for(rel, path)
            label = label_for(rel, path)
        except Exception:
            return
        file.add_emblem(emblem)
        file.add_string_attribute("omgee_status", label)

    def get_file_items(self, *args):
        files = args[0] if len(args) == 1 else args[1]
        if not self._omgee():
            return []
        selected = self._selected(files)
        if not selected:
            return []

        stubs = [pair for pair in selected if _stub(pair[1])]
        rest = [pair for pair in selected if pair not in stubs]
        items = []

        if stubs:
            item = Nautilus.MenuItem(
                name="OmgeeDrive::open",
                label="Open in browser"
                if len(stubs) == 1
                else f"Open {len(stubs)} shortcuts in browser",
                icon="web-browser",
            )
            item.connect("activate", self._on_open, stubs)
            items.append(item)

        pinned = []
        unpinned = []
        for pair in rest:
            rel = _rel(pair[1], _mount_point())
            if rel is None:
                continue
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
                icon="folder-download",
            )
            item.connect("activate", self._on_pin, unpinned)
            items.append(item)

        if pinned:
            item = Nautilus.MenuItem(
                name="OmgeeDrive::unpin",
                label="Free up space"
                if len(pinned) == 1
                else f"Free space for {len(pinned)} items",
                icon="folder-remote",
            )
            item.connect("activate", self._on_unpin, pinned)
            items.append(item)

        return items

    def _on_pin(self, _menu, pairs):
        self._run("pin", pairs)

    def _on_unpin(self, _menu, pairs):
        self._run("unpin", pairs)

    def _on_open(self, _menu, pairs):
        binary = self._omgee()
        if not binary:
            return
        for _file, path in pairs:
            Gio.Subprocess.new(
                [binary, "open", str(path)], Gio.SubprocessFlags.NONE
            )
