import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

DEFAULT_STORAGE_PATH = "/srv/rpinas/NAS"
ALLOWED_STORAGE_ROOTS = ("/srv/rpinas", "/media", "/mnt", "/run/media")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass
class StorageDevice:
    name: str
    path: str
    size: str
    mountpoint: str | None
    fstype: str | None
    removable: bool
    is_sd_card: bool


def detect_storage_devices() -> list[StorageDevice]:
    try:
        out = subprocess.check_output(["lsblk", "-J", "-o", "NAME,SIZE,MOUNTPOINT,FSTYPE,RM,TRAN"], text=True)
        parsed = json.loads(out)
    except Exception:
        return []

    devices: list[StorageDevice] = []
    for block in parsed.get("blockdevices", []):
        path = f"/dev/{block['name']}"
        transport = (block.get("tran") or "").lower()
        devices.append(
            StorageDevice(
                name=block["name"],
                path=path,
                size=block.get("size", "unknown"),
                mountpoint=block.get("mountpoint"),
                fstype=block.get("fstype"),
                removable=bool(block.get("rm", False)),
                is_sd_card=transport == "mmc",
            )
        )
    return devices


def normalize_storage_path(path: str) -> str:
    normalized = os.path.realpath(path)
    if not os.path.isabs(normalized):
        raise ValueError("Storage path must be absolute")
    if not any(normalized == root or normalized.startswith(f"{root}/") for root in ALLOWED_STORAGE_ROOTS):
        raise ValueError("Storage path must be under /srv/rpinas, /media, /mnt, or /run/media")
    return normalized


def _validate_username(username: str) -> str:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Invalid username")
    return username


def ensure_nas_structure(base_path: str, usernames: list[str]) -> None:
    base_path = normalize_storage_path(base_path)
    shared = os.path.join(base_path, "Shared")
    users = os.path.join(base_path, "Users")
    os.makedirs(shared, exist_ok=True)  # codeql[py/path-injection]
    os.makedirs(users, exist_ok=True)  # codeql[py/path-injection]
    os.chmod(shared, 0o777)  # codeql[py/path-injection]
    for username in usernames:
        user_dir = os.path.join(users, _validate_username(username))
        os.makedirs(user_dir, exist_ok=True)  # codeql[py/path-injection]
        os.chmod(user_dir, 0o770)  # codeql[py/path-injection]


def migrate_storage(old_path: str, new_path: str) -> None:
    old_path = normalize_storage_path(old_path)
    new_path = normalize_storage_path(new_path)
    if old_path == new_path or not os.path.isdir(old_path):
        return
    os.makedirs(new_path, exist_ok=True)  # codeql[py/path-injection]
    subprocess.run(["rsync", "-a", f"{old_path}/", f"{new_path}/"], check=False)


def disk_usage(path: str) -> dict[str, Any]:
    path = normalize_storage_path(path)
    total, used, free = shutil.disk_usage(path)  # codeql[py/path-injection]
    return {
        "total": total,
        "used": used,
        "free": free,
        "used_pct": round((used / total) * 100, 2) if total else 0,
    }
