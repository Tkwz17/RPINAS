import os
import secrets
import subprocess
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_config, get_conn, init_db, log_event, set_config
from .network import apply_network_services, configure_access_point, set_static_ap_address
from .samba import apply_samba, delete_samba_user, set_samba_password, write_samba_config
from .storage import (
    DEFAULT_STORAGE_PATH,
    detect_storage_devices,
    disk_usage,
    ensure_nas_structure,
    migrate_storage,
    normalize_storage_path,
)

SESSION_TTL_HOURS = 24


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_valid(session_id: str | None) -> bool:
    if not session_id:
        return False
    with get_conn() as conn:
        row = conn.execute("SELECT expires_at FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return False
    return _now() < datetime.fromisoformat(row["expires_at"])


def require_auth(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        token = request.cookies.get("rpinas_session")
        if not _session_valid(token):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapped


def _get_users() -> list[dict[str, str]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT username, created_at FROM nas_users ORDER BY username").fetchall()
    return [{"username": row["username"], "created_at": row["created_at"]} for row in rows]


def _get_usernames() -> list[str]:
    return [entry["username"] for entry in _get_users()]


def _create_session() -> str:
    session_id = secrets.token_urlsafe(32)
    created_at = _now()
    expires_at = created_at + timedelta(hours=SESSION_TTL_HOURS)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, created_at, expires_at) VALUES (?, ?, ?)",
            (session_id, created_at.isoformat(), expires_at.isoformat()),
        )
    return session_id


def _clear_session(session_id: str | None) -> None:
    if not session_id:
        return
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def _bootstrap_defaults() -> None:
    if get_config("guest_enabled") is None:
        set_config("guest_enabled", False)
    if get_config("wifi_ssid") is None:
        set_config("wifi_ssid", "RPINAS")
    if get_config("wifi_password") is None:
        set_config("wifi_password", "")
    if get_config("storage_path") is None:
        set_config("storage_path", DEFAULT_STORAGE_PATH)
    if get_config("setup_complete") is None:
        set_config("setup_complete", False)


def _configure_nas_runtime(storage_path: str, guest_enabled: bool) -> None:
    usernames = _get_usernames()
    ensure_nas_structure(storage_path, usernames)
    write_samba_config(storage_path, usernames, guest_enabled)
    apply_samba()


def _configure_wifi_runtime(ssid: str, password: str | None) -> None:
    set_static_ap_address()
    configure_access_point(ssid, password)
    apply_network_services()


def _safe_storage_path() -> str:
    raw = str(get_config("storage_path", DEFAULT_STORAGE_PATH))
    try:
        return normalize_storage_path(raw)
    except ValueError:
        return DEFAULT_STORAGE_PATH


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config["JSON_SORT_KEYS"] = False

    init_db()
    _bootstrap_defaults()

    @app.get("/api/status")
    def status() -> Any:
        storage_path = _safe_storage_path()
        setup_complete = bool(get_config("setup_complete", False))
        usage = disk_usage(storage_path) if os.path.isdir(storage_path) else {"total": 0, "used": 0, "free": 0, "used_pct": 0}
        return jsonify(
            {
                "setup_complete": setup_complete,
                "wifi_ssid": get_config("wifi_ssid", "RPINAS"),
                "storage_path": storage_path,
                "guest_enabled": bool(get_config("guest_enabled", False)),
                "storage_usage": usage,
                "network_ip": "192.168.4.1",
                "connected_users": len(_get_users()),
            }
        )

    @app.post("/api/setup")
    def setup() -> Any:
        if bool(get_config("setup_complete", False)):
            return jsonify({"error": "Setup already completed"}), 400

        payload = request.get_json(silent=True) or {}
        admin_password = payload.get("admin_password", "")
        users = payload.get("users", [])
        guest_enabled = bool(payload.get("guest_enabled", False))
        selected_storage = str(payload.get("storage_path", DEFAULT_STORAGE_PATH)).strip()

        if len(admin_password) < 8:
            return jsonify({"error": "Admin password must be at least 8 characters"}), 400
        if not users:
            return jsonify({"error": "At least one NAS user is required"}), 400
        try:
            selected_storage = normalize_storage_path(selected_storage)
        except ValueError:
            return jsonify({"error": "Invalid storage path"}), 400

        validated_users = []
        seen = set()
        for entry in users:
            username = str(entry.get("username", "")).strip()
            password = str(entry.get("password", "")).strip()
            if not username or not password:
                return jsonify({"error": "Each user requires username and password"}), 400
            if username in seen:
                return jsonify({"error": "Duplicate usernames are not allowed"}), 400
            seen.add(username)
            validated_users.append({"username": username, "password": password})

        set_config("admin_password_hash", generate_password_hash(admin_password))
        set_config("guest_enabled", guest_enabled)
        set_config("storage_path", selected_storage)
        set_config("setup_complete", True)

        with get_conn() as conn:
            for entry in validated_users:
                conn.execute(
                    "INSERT OR REPLACE INTO nas_users (username, password_hash, created_at) VALUES (?, ?, datetime('now'))",
                    (entry["username"], generate_password_hash(entry["password"])),
                )

        for entry in validated_users:
            set_samba_password(entry["username"], entry["password"])

        _configure_nas_runtime(selected_storage, guest_enabled)
        _configure_wifi_runtime(get_config("wifi_ssid", "RPINAS"), get_config("wifi_password", "") or None)
        log_event("setup_complete", {"users": [u["username"] for u in validated_users], "storage_path": selected_storage})
        return jsonify({"ok": True})

    @app.post("/api/login")
    def login() -> Any:
        payload = request.get_json(silent=True) or {}
        password = payload.get("password", "")
        admin_hash = get_config("admin_password_hash")
        if not admin_hash or not check_password_hash(admin_hash, password):
            return jsonify({"error": "Invalid credentials"}), 401

        token = _create_session()
        response = jsonify({"ok": True})
        response.set_cookie("rpinas_session", token, httponly=True, secure=False, samesite="Strict", max_age=SESSION_TTL_HOURS * 3600)
        return response

    @app.post("/api/logout")
    @require_auth
    def logout() -> Any:
        token = request.cookies.get("rpinas_session")
        _clear_session(token)
        response = jsonify({"ok": True})
        response.delete_cookie("rpinas_session")
        return response

    @app.get("/api/storage/devices")
    @require_auth
    def storage_devices() -> Any:
        devices = [device.__dict__ for device in detect_storage_devices()]
        return jsonify({"devices": devices})

    @app.get("/api/dashboard")
    @require_auth
    def dashboard() -> Any:
        storage_path = _safe_storage_path()
        logs = []
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT event_type, details, created_at FROM audit_logs ORDER BY id DESC LIMIT 20"
            ).fetchall()
            logs = [{"event_type": r["event_type"], "details": r["details"], "created_at": r["created_at"]} for r in rows]

        return jsonify(
            {
                "storage_usage": disk_usage(storage_path) if os.path.isdir(storage_path) else {"total": 0, "used": 0, "free": 0, "used_pct": 0},
                "users": _get_users(),
                "network": {"ssid": get_config("wifi_ssid", "RPINAS"), "ip": "192.168.4.1"},
                "system": {"setup_complete": bool(get_config("setup_complete", False)), "service": "running"},
                "logs": logs,
            }
        )

    @app.get("/api/users")
    @require_auth
    def users_list() -> Any:
        return jsonify({"users": _get_users(), "guest_enabled": bool(get_config("guest_enabled", False))})

    @app.post("/api/users")
    @require_auth
    def users_add() -> Any:
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        with get_conn() as conn:
            exists = conn.execute("SELECT username FROM nas_users WHERE username = ?", (username,)).fetchone()
            if exists:
                return jsonify({"error": "User already exists"}), 400
            conn.execute(
                "INSERT INTO nas_users (username, password_hash, created_at) VALUES (?, ?, datetime('now'))",
                (username, generate_password_hash(password)),
            )

        set_samba_password(username, password)
        _configure_nas_runtime(_safe_storage_path(), bool(get_config("guest_enabled", False)))
        log_event("user_added", {"username": username})
        return jsonify({"ok": True})

    @app.delete("/api/users/<username>")
    @require_auth
    def users_delete(username: str) -> Any:
        with get_conn() as conn:
            conn.execute("DELETE FROM nas_users WHERE username = ?", (username,))
        delete_samba_user(username)
        _configure_nas_runtime(_safe_storage_path(), bool(get_config("guest_enabled", False)))
        log_event("user_deleted", {"username": username})
        return jsonify({"ok": True})

    @app.post("/api/users/<username>/reset-password")
    @require_auth
    def users_reset_password(username: str) -> Any:
        payload = request.get_json(silent=True) or {}
        password = str(payload.get("password", "")).strip()
        if not password:
            return jsonify({"error": "Password is required"}), 400

        with get_conn() as conn:
            row = conn.execute("SELECT username FROM nas_users WHERE username = ?", (username,)).fetchone()
            if not row:
                return jsonify({"error": "User not found"}), 404
            conn.execute("UPDATE nas_users SET password_hash = ? WHERE username = ?", (generate_password_hash(password), username))
        set_samba_password(username, password)
        log_event("user_password_reset", {"username": username})
        return jsonify({"ok": True})

    @app.post("/api/users/guest")
    @require_auth
    def users_guest() -> Any:
        payload = request.get_json(silent=True) or {}
        enabled = bool(payload.get("enabled", False))
        set_config("guest_enabled", enabled)
        _configure_nas_runtime(_safe_storage_path(), enabled)
        log_event("guest_access_updated", {"enabled": enabled})
        return jsonify({"ok": True})

    @app.get("/api/network")
    @require_auth
    def network_get() -> Any:
        return jsonify({"ssid": get_config("wifi_ssid", "RPINAS"), "password_set": bool(get_config("wifi_password", ""))})

    @app.post("/api/network")
    @require_auth
    def network_set() -> Any:
        payload = request.get_json(silent=True) or {}
        ssid = str(payload.get("ssid", "")).strip()
        password = str(payload.get("password", ""))
        if not ssid:
            return jsonify({"error": "SSID is required"}), 400
        if password and len(password) < 8:
            return jsonify({"error": "WiFi password must be at least 8 characters"}), 400

        set_config("wifi_ssid", ssid)
        set_config("wifi_password", password)
        _configure_wifi_runtime(ssid, password or None)
        log_event("network_updated", {"ssid": ssid, "password_set": bool(password)})
        return jsonify({"ok": True, "reboot_required": True})

    @app.get("/api/storage")
    @require_auth
    def storage_get() -> Any:
        path = _safe_storage_path()
        usage = disk_usage(path) if os.path.isdir(path) else {"total": 0, "used": 0, "free": 0, "used_pct": 0}
        return jsonify({"storage_path": path, "usage": usage})

    @app.post("/api/storage")
    @require_auth
    def storage_set() -> Any:
        payload = request.get_json(silent=True) or {}
        new_path = str(payload.get("storage_path", "")).strip()
        if not new_path:
            return jsonify({"error": "Storage path required"}), 400
        try:
            new_path = normalize_storage_path(new_path)
        except ValueError:
            return jsonify({"error": "Invalid storage path"}), 400

        old_path = _safe_storage_path()
        migrate_storage(old_path, new_path)
        set_config("storage_path", new_path)
        _configure_nas_runtime(new_path, bool(get_config("guest_enabled", False)))
        log_event("storage_updated", {"old": old_path, "new": new_path})
        return jsonify({"ok": True})

    @app.get("/api/system/logs")
    @require_auth
    def system_logs() -> Any:
        try:
            out = subprocess.check_output(["journalctl", "-u", "rpinas-backend.service", "-n", "200", "--no-pager"], text=True)
            lines = out.splitlines()
        except Exception:
            lines = ["Unable to load system logs in current environment."]
        return jsonify({"logs": lines})

    @app.post("/api/system/reboot")
    @require_auth
    def system_reboot() -> Any:
        subprocess.run(["systemctl", "reboot"], check=False)
        log_event("system_reboot", {})
        return jsonify({"ok": True})

    @app.post("/api/system/shutdown")
    @require_auth
    def system_shutdown() -> Any:
        subprocess.run(["systemctl", "poweroff"], check=False)
        log_event("system_shutdown", {})
        return jsonify({"ok": True})

    @app.get("/")
    def serve_ui() -> Any:
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/<path:path>")
    def static_proxy(path: str) -> Any:
        static_file = os.path.join(app.static_folder, path)
        if os.path.isfile(static_file):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8080)
