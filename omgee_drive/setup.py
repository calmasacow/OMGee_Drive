from __future__ import annotations

import shutil
import subprocess

from omgee_drive.paths import (
    LOCAL_DIR,
    RCLONE_CONF,
    REMOTE_DRIVE,
    REMOTE_LOCAL,
    REMOTE_UNION,
    ensure_dirs,
)
from omgee_drive import config as cfg
from omgee_drive import rclone


def _conf_text() -> str:
    if RCLONE_CONF.exists():
        return RCLONE_CONF.read_text(encoding="utf-8")
    return ""


def _has_section(name: str) -> bool:
    return f"[{name}]" in _conf_text()


def ensure_rclone_package() -> None:
    if shutil.which("rclone"):
        return
    print("rclone is missing. Installing with omarchy pkg add rclone …")
    cmd = ["omarchy", "pkg", "add", "rclone"]
    proc = subprocess.run(cmd)
    if proc.returncode != 0 or not shutil.which("rclone"):
        raise SystemExit(
            "Could not install rclone. Run: omarchy pkg add rclone"
        )


def write_overlay_remotes() -> None:
    ensure_dirs()
    text = _conf_text()
    if not _has_section(REMOTE_LOCAL):
        block = (
            f"\n[{REMOTE_LOCAL}]\n"
            f"type = alias\n"
            f"remote = {LOCAL_DIR}\n"
        )
        RCLONE_CONF.write_text(text + block, encoding="utf-8")
        text = _conf_text()
    if not _has_section(REMOTE_UNION):
        block = (
            f"\n[{REMOTE_UNION}]\n"
            f"type = union\n"
            f"upstreams = {REMOTE_LOCAL}::nc {REMOTE_DRIVE}:\n"
            f"search_policy = ff\n"
            f"create_policy = epff\n"
            f"action_policy = epff\n"
        )
        RCLONE_CONF.write_text(text + block, encoding="utf-8")


def configure_drive(client_id: str | None, client_secret: str | None) -> None:
    ensure_dirs()
    args = [
        rclone.rclone_bin(),
        "--config",
        str(RCLONE_CONF),
        "config",
        "create",
        REMOTE_DRIVE,
        "drive",
        "skip_gdocs",
        "true",
        "scope",
        "drive",
    ]
    if client_id:
        args.extend(["client_id", client_id])
    if client_secret:
        args.extend(["client_secret", client_secret])
    print("A browser will open so Google can authorize OMGee Drive.")
    print("Sign in, then come back here.\n")
    proc = subprocess.run(args)
    if proc.returncode != 0:
        raise SystemExit("rclone Google Drive login failed.")
    # Recreate overlay remotes after rclone rewrites the file.
    write_overlay_remotes()


def setup(client_id: str | None = None, client_secret: str | None = None) -> None:
    ensure_rclone_package()
    ensure_dirs()
    cfg.load()
    mount = cfg.mount_point()
    mount.mkdir(parents=True, exist_ok=True)
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    if not rclone.has_token():
        configure_drive(client_id, client_secret)
    else:
        print("Google Drive is already authorized.")
        write_overlay_remotes()

    print(f"\nMount point: {mount}")
    print("Start it with:  omgee-drive start")
    print("Or:             systemctl --user start --now omgee-drive.service")
