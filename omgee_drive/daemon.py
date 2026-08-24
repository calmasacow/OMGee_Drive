from __future__ import annotations

import signal
import subprocess
import sys
import threading

from pathlib import Path

from omgee_drive import config as cfg
from omgee_drive import pins
from omgee_drive import rclone
from omgee_drive import status as st
from omgee_drive import stubs
from omgee_drive.paths import REMOTE_DRIVE, REMOTE_UNION, ensure_dirs


_stop = threading.Event()
_mount_proc: subprocess.Popen[str] | None = None


def _loop(name: str, interval: int, fn, delay: int = 0) -> None:
    if delay and _stop.wait(delay):
        return
    while not _stop.is_set():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — daemon must stay up
            print(f"omgee-drive: {name} failed: {exc}", file=sys.stderr)
        if _stop.wait(interval):
            break


def _unmount(mount: Path) -> None:
    global _mount_proc
    if _mount_proc and _mount_proc.poll() is None:
        _mount_proc.send_signal(signal.SIGINT)
        try:
            _mount_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _mount_proc.kill()
    _mount_proc = None
    subprocess.run(
        ["fusermount3", "-u", str(mount)],
        check=False,
        capture_output=True,
    )


def unmount() -> None:
    _unmount(cfg.mount_point())


def run() -> None:
    global _mount_proc
    if not rclone.has_token():
        raise SystemExit("Not authorized. Run: omgee-drive setup")

    ensure_dirs()
    conf = cfg.load()
    mount = cfg.mount_point()
    mount.mkdir(parents=True, exist_ok=True)

    def handle_stop(_signum, _frame):
        _stop.set()
        _unmount(mount)

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    cmd = rclone.mount_cmd(f"{REMOTE_UNION}:", mount)
    print("Mounting", mount)
    _mount_proc = subprocess.Popen(cmd)

    stub_thread = threading.Thread(
        target=_loop,
        args=("stubs", int(conf["stub_refresh_sec"]), stubs.refresh),
        daemon=True,
    )
    share_thread = threading.Thread(
        target=_loop,
        kwargs={
            "name": "sharing",
            "interval": max(int(conf["stub_refresh_sec"]) * 4, 1200),
            "fn": lambda: stubs.refresh(with_sharing=True),
            "delay": 45,
        },
        daemon=True,
    )
    pin_thread = threading.Thread(
        target=_loop,
        kwargs={
            "name": "pins",
            "interval": int(conf["pin_sync_sec"]),
            "fn": pins.sync_pins,
            "delay": 20,
        },
        daemon=True,
    )

    def check_link():
        st.set_offline(not rclone.reachable(f"{REMOTE_DRIVE}:"))

    link_thread = threading.Thread(
        target=_loop,
        kwargs={"name": "link", "interval": 60, "fn": check_link, "delay": 5},
        daemon=True,
    )
    stub_thread.start()
    share_thread.start()
    pin_thread.start()
    link_thread.start()

    assert _mount_proc is not None
    rc = _mount_proc.wait()
    _stop.set()
    _unmount(mount)
    if rc not in (0, -signal.SIGINT, -signal.SIGTERM):
        raise SystemExit(f"rclone mount exited {rc}")
