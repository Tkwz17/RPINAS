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
            "storage_path": "/tmp/nas",
        },
    )
    assert response.status_code == 400
