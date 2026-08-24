from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from omgee_drive import __version__
from omgee_drive import config as cfg
from omgee_drive import daemon
from omgee_drive import pins
from omgee_drive import rclone
from omgee_drive import setup as setup_mod
from omgee_drive import stubs
from omgee_drive.paths import LOCAL_DIR, RCLONE_CONF


def _notify(title: str, body: str) -> None:
    notify = shutil.which("notify-send")
    if notify:
        subprocess.run([notify, "-a", "OMGee Drive", title, body], check=False)


def cmd_setup(args: argparse.Namespace) -> None:
    setup_mod.setup(args.client_id, args.client_secret)


def cmd_start(_args: argparse.Namespace) -> None:
    unit = subprocess.run(
        ["systemctl", "--user", "enable", "--now", "omgee-drive.service"],
        check=False,
    )
    if unit.returncode != 0:
        print("systemd user unit not installed; running daemon in the foreground.")
        daemon.run()


def cmd_stop(_args: argparse.Namespace) -> None:
    subprocess.run(
        ["systemctl", "--user", "stop", "omgee-drive.service"], check=False
    )
    daemon.unmount()
    print("Stopped.")


def cmd_status(_args: argparse.Namespace) -> None:
    mount = cfg.mount_point()
    print(f"version:     {__version__}")
    print(f"authorized:  {rclone.has_token()}")
    print(f"rclone.conf: {RCLONE_CONF}")
    print(f"mount:       {mount}")
    print(f"local pins:  {LOCAL_DIR}")
    print(f"pins:        {len(pins.load_pins())}")
    mounted = mount.exists() and mount.is_mount()
    print(f"mounted:     {mounted}")
    subprocess.run(["systemctl", "--user", "is-active", "omgee-drive.service"])


def cmd_daemon(_args: argparse.Namespace) -> None:
    daemon.run()


def cmd_pin(args: argparse.Namespace) -> None:
    paths = [Path(p) for p in args.paths]
    added = pins.pin(paths)
    msg = (
        f"Kept {len(added)} item(s) offline"
        if added
        else "Nothing new to pin (Docs/Sheets are always shortcuts)"
    )
    print(msg)
    if args.notify:
        _notify("OMGee Drive", msg)


def cmd_unpin(args: argparse.Namespace) -> None:
    paths = [Path(p) for p in args.paths]
    removed = pins.unpin(paths)
    msg = f"Freed {len(removed)} item(s)" if removed else "Nothing to free"
    print(msg)
    if args.notify:
        _notify("OMGee Drive", msg)


def cmd_open(args: argparse.Namespace) -> None:
    path = Path(args.path)
    data = stubs.read_stub(path)
    if data and data.get("url"):
        subprocess.run(["xdg-open", data["url"]], check=False)
        return
    if not path.exists():
        raise SystemExit(f"No such file: {path}")
    subprocess.run(["xdg-open", str(path)], check=False)


def cmd_refresh(_args: argparse.Namespace) -> None:
    written, removed = stubs.refresh()
    print(f"Stubs written: {written}, stale removed: {removed}")


def cmd_unmount(_args: argparse.Namespace) -> None:
    daemon.unmount()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="omgee-drive",
        description="Dropbox-like Google Drive folder for Omarchy.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="Authorize Google Drive (opens a browser)")
    s.add_argument("--client-id", help="Your Google Cloud OAuth client ID")
    s.add_argument("--client-secret", help="Your Google Cloud OAuth client secret")
    s.set_defaults(func=cmd_setup)

    sub.add_parser("start", help="Enable and start the user service").set_defaults(
        func=cmd_start
    )
    sub.add_parser("stop", help="Stop the mount").set_defaults(func=cmd_stop)
    sub.add_parser("status", help="Show mount and auth state").set_defaults(
        func=cmd_status
    )
    sub.add_parser("daemon", help="Run mount + stub refresh in the foreground").set_defaults(
        func=cmd_daemon
    )
    sub.add_parser("unmount", help="Unmount without disabling the service").set_defaults(
        func=cmd_unmount
    )
    sub.add_parser("refresh-stubs", help="Rebuild Docs/Sheets shortcut files").set_defaults(
        func=cmd_refresh
    )

    pin_p = sub.add_parser("pin", help="Make a file or folder available offline")
    pin_p.add_argument("paths", nargs="+")
    pin_p.add_argument("--notify", action="store_true")
    pin_p.set_defaults(func=cmd_pin)

    unpin_p = sub.add_parser("unpin", help="Free local space (file stays in Drive)")
    unpin_p.add_argument("paths", nargs="+")
    unpin_p.add_argument("--notify", action="store_true")
    unpin_p.set_defaults(func=cmd_unpin)

    open_p = sub.add_parser("open", help="Open a .gdoc/.gsheet shortcut in the browser")
    open_p.add_argument("path")
    open_p.set_defaults(func=cmd_open)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (rclone.RcloneError, ValueError) as exc:
        print(f"omgee-drive: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
