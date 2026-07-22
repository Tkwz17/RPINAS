import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

DEFAULT_STORAGE_PATH = "/srv/rpinas/NAS"


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


def ensure_nas_structure(base_path: str, usernames: list[str]) -> None:
    shared = os.path.join(base_path, "Shared")
    users = os.path.join(base_path, "Users")
    os.makedirs(shared, exist_ok=True)
    os.makedirs(users, exist_ok=True)
    os.chmod(shared, 0o777)
    for username in usernames:
        user_dir = os.path.join(users, username)
        os.makedirs(user_dir, exist_ok=True)
        os.chmod(user_dir, 0o770)


def migrate_storage(old_path: str, new_path: str) -> None:
    if old_path == new_path or not os.path.isdir(old_path):
        return
    os.makedirs(new_path, exist_ok=True)
    subprocess.run(["rsync", "-a", f"{old_path}/", f"{new_path}/"], check=False)


def disk_usage(path: str) -> dict[str, Any]:
    total, used, free = shutil.disk_usage(path)
    return {
        "total": total,
        "used": used,
        "free": free,
        "used_pct": round((used / total) * 100, 2) if total else 0,
    }
