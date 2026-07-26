from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_image_workflow_runs_on_main_and_MAIN_pushes():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")

    assert "branches: [ main, MAIN ]" in workflow


def test_network_setup_service_only_runs_until_configured_marker_exists():
    unit = (REPO_ROOT / "systemd/rpinas-network-setup.service").read_text(encoding="utf-8")

    assert "ConditionPathExists=!/var/lib/rpinas/.network_configured" in unit
