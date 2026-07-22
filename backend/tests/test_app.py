import os
import tempfile

import pytest

os.environ["RPINAS_DB_PATH"] = tempfile.mktemp(prefix="rpinas-test-", suffix=".db")

from backend.app import create_app  # noqa: E402


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


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
            "storage_path": "/tmp/nas",
        },
    )
    assert response.status_code == 400
