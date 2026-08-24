from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from omgee_drive.paths import CACHE_DIR, RCLONE_CONF


class RcloneError(RuntimeError):
    pass


def rclone_bin() -> str:
    path = shutil.which("rclone")
    if not path:
        raise RcloneError(
            "rclone is not installed. On Omarchy: omarchy pkg add rclone"
        )
    return path


def run(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [rclone_bin(), "--config", str(RCLONE_CONF), *args]
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        cmd,
        check=False,
        text=True,
        capture_output=capture,
        env=env,
    )
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RcloneError(err or f"rclone failed: {' '.join(cmd)}")
    return proc


def configured() -> bool:
    return RCLONE_CONF.exists() and "[omgee-gdrive]" in RCLONE_CONF.read_text(
        encoding="utf-8"
    )


def has_token() -> bool:
    if not configured():
        return False
    text = RCLONE_CONF.read_text(encoding="utf-8")
    return "token" in text and "access_token" in text


def stat(remote: str) -> dict | None:
    proc = run(["lsjson", remote, "--stat"], check=False)
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    data = json.loads(proc.stdout)
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def reachable(remote: str) -> bool:
    proc = run(["lsf", remote, "--max-depth", "1"], check=False)
    return proc.returncode == 0


def lsjson(remote: str, extra: list[str] | None = None) -> list[dict]:
    args = [
        "lsjson",
        remote,
        "--recursive",
        "--files-only",
        "--fast-list",
        *(extra or []),
    ]
    proc = run(args)
    if not proc.stdout.strip():
        return []
    return json.loads(proc.stdout)


def copyto(src: str, dest: str) -> None:
    run(["copyto", src, dest])


def copy_tree(src: str, dest: str, extra: list[str] | None = None) -> None:
    run(["copy", src, dest, "--create-empty-src-dirs", *(extra or [])])


def mount_cmd(union_remote: str, mount_point: Path) -> list[str]:
    return [
        rclone_bin(),
        "--config",
        str(RCLONE_CONF),
        "mount",
        union_remote,
        str(mount_point),
        "--vfs-cache-mode",
        "full",
        "--vfs-cache-max-age",
        "720h",
        "--vfs-write-back",
        "5s",
        "--dir-cache-time",
        "5m",
        "--poll-interval",
        "1m",
        "--cache-dir",
        str(CACHE_DIR),
        "--umask",
        "022",
    ]
