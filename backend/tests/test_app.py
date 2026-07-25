import os
import tempfile

import pytest

TEST_DB_FILE = tempfile.NamedTemporaryFile(prefix="rpinas-test-", suffix=".db", delete=False)
TEST_DB_FILE.close()
os.environ["RPINAS_DB_PATH"] = TEST_DB_FILE.name

from backend.app import create_app  # noqa: E402


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    if os.path.exists(TEST_DB_FILE.name):
        os.remove(TEST_DB_FILE.name)


def test_status_endpoint(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["wifi_ssid"] == "RPINAS"
    assert payload["network_ip"] == "192.168.4.1"


def test_setup_requires_user(client):
    response = client.post(
        "/api/setup",
        json={
            "admin_password": "strong-pass-123",
            "users": [],
            "guest_enabled": False,
            "storage_target": "sd",
        },
    )
    assert response.status_code == 400


def test_setup_does_not_mark_complete_when_runtime_configuration_fails(client, monkeypatch):
    from backend import app as app_module

    monkeypatch.setattr(app_module, "set_samba_password", lambda username, password: None)
    monkeypatch.setattr(app_module, "_configure_nas_runtime", lambda storage_path, guest_enabled: None)

    def fail_wifi(ssid, password):
        raise RuntimeError("wifi failed")

    monkeypatch.setattr(app_module, "_configure_wifi_runtime", fail_wifi)

    with pytest.raises(RuntimeError, match="wifi failed"):
        client.post(
            "/api/setup",
            json={
                "admin_password": "strong-pass-123",
                "users": [{"username": "alice", "password": "user-pass-123"}],
                "guest_enabled": False,
                "storage_target": "sd",
            },
        )

    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.get_json()["setup_complete"] is False
