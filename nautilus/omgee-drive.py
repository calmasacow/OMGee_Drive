"""Nautilus right-click: Make available offline / Free up space."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from gi import require_version

require_version("Nautilus", "4.1")

from gi.repository import Gio, GObject, Nautilus  # noqa: E402

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


def _local_dir() -> Path:
    return Path.home() / ".local" / "share" / "omgee-drive" / "local"


def _pins() -> set[str]:
    pins_file = Path.home() / ".local" / "share" / "omgee-drive" / "pins.json"
    if not pins_file.exists():
        return set()
    try:
        return set(json.loads(pins_file.read_text(encoding="utf-8")).get("paths", []))
    except json.JSONDecodeError:
        return set()


def _rel(path: Path, mount: Path) -> str | None:
    try:
        return str(path.resolve().relative_to(mount.resolve())).replace("\\", "/")
    except ValueError:
        return None


def _is_stub(path: Path) -> bool:
    return path.suffix.lower() in STUB_SUFFIXES


def _is_pinned(rel: str, pinset: set[str]) -> bool:
    if rel in pinset:
        return True
    parts = rel.split("/")
    for i in range(1, len(parts)):
        if "/".join(parts[:i]) in pinset:
            return True
    local = _local_dir() / rel
    return local.exists() and not _is_stub(local)


class OmgeeDriveMenu(GObject.GObject, Nautilus.MenuProvider):
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
            path = location.get_path()
            if not path:
                continue
            p = Path(path)
            if _rel(p, mount) is None:
                continue
            paths.append(p)
        return paths

    def _run(self, subcmd: str, paths: list[Path]):
        binary = self._omgee()
        if not binary:
            return
        Gio.Subprocess.new(
            [binary, subcmd, "--notify", *[str(p) for p in paths]],
            Gio.SubprocessFlags.NONE,
        )

    def get_file_items(self, *args):
        files = args[0] if len(args) == 1 else args[1]
        if not self._omgee():
            return []
        paths = self._selected(files)
        if not paths:
            return []

        mount = _mount_point()
        pinset = _pins()
        stubs = [p for p in paths if _is_stub(p)]
        rest = [p for p in paths if p not in stubs]
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
        for p in rest:
            rel = _rel(p, mount)
            if rel is None:
                continue
            if _is_pinned(rel, pinset):
                pinned.append(p)
            else:
                unpinned.append(p)

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

    def _on_pin(self, _menu, paths):
        self._run("pin", paths)

    def _on_unpin(self, _menu, paths):
        self._run("unpin", paths)

    def _on_open(self, _menu, paths):
        binary = self._omgee()
        if not binary:
            return
        for path in paths:
            Gio.Subprocess.new(
                [binary, "open", str(path)], Gio.SubprocessFlags.NONE
            )
