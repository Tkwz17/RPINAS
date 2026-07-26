import os
import pwd
import re
import subprocess

SAMBA_CONF = "/etc/samba/smb.conf"
USERNAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def _validate_username(username: str) -> str:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Invalid username")
    return username


def _system_user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def ensure_system_user(username: str) -> None:
    username = _validate_username(username)
    if not _system_user_exists(username):
        subprocess.run(["useradd", "-M", "-s", "/usr/sbin/nologin", username], check=True)


def set_samba_password(username: str, password: str) -> None:
    username = _validate_username(username)
    ensure_system_user(username)
    # Pass the password via stdin rather than interpolating it into a shell
    # string, so passwords containing quotes/special characters can't break
    # or inject into the command.
    stdin_data = f"{password}\n{password}\n"
    subprocess.run(["smbpasswd", "-a", "-s", username], input=stdin_data, text=True, check=True)


def delete_samba_user(username: str) -> None:
    username = _validate_username(username)
    subprocess.run(["smbpasswd", "-x", username], check=False)
    subprocess.run(["userdel", username], check=False)


def write_samba_config(storage_path: str, usernames: list[str], guest_enabled: bool) -> None:
    shared_path = os.path.join(storage_path, "Shared")
    users_path = os.path.join(storage_path, "Users")

    config = [
        "[global]",
        "   workgroup = WORKGROUP",
        "   server string = RPINAS",
        "   map to guest = Bad User",
        "   guest account = nobody",
        "   security = user",
        "   passdb backend = tdbsam",
        "",
        "[Shared]",
        f"   path = {shared_path}",
        "   browseable = yes",
        "   writable = yes",
        f"   guest ok = {'yes' if guest_enabled else 'no'}",
        "   create mask = 0666",
        "   directory mask = 0777",
        "",
    ]

    for username in usernames:
        config.extend(
            [
                f"[{username}]",
                f"   path = {os.path.join(users_path, username)}",
                "   browseable = yes",
                "   writable = yes",
                f"   valid users = {username}",
                "   guest ok = no",
                "   create mask = 0660",
                "   directory mask = 0770",
                "",
            ]
        )

    with open(SAMBA_CONF, "w", encoding="utf-8") as f:
        f.write("\n".join(config))


def apply_samba() -> None:
    subprocess.run(["testparm", "-s", SAMBA_CONF], stdout=subprocess.DEVNULL, check=True)
    subprocess.run(["systemctl", "enable", "smbd", "nmbd"], check=True)
    subprocess.run(["systemctl", "restart", "smbd", "nmbd"], check=True)
    subprocess.run(["systemctl", "is-active", "--quiet", "smbd"], check=True)
