from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_image_workflow_runs_on_main_and_MAIN_pushes():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")

    assert "branches: [ main, MAIN ]" in workflow


def test_network_setup_service_only_runs_until_configured_marker_exists():
    unit = (REPO_ROOT / "systemd/rpinas-network-setup.service").read_text(encoding="utf-8")

    assert "ConditionPathExists=!/var/lib/rpinas/.network_configured" in unit


def test_image_workflow_uses_model_specific_boot_tuning():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")

    assert "[pi3]" in workflow
    assert "arm_64bit=0" in workflow
    assert "[pi4]" in workflow
    assert "[pi5]" in workflow
    assert "dtparam=pciex1" in workflow


def test_model_env_files_include_device_hardware_profiles():
    expected = {
        "rpinas-pi3.env": ("RPINAS_BOARD=pi3", "RPINAS_SOC=BCM2837", "RPINAS_PRIMARY_STORAGE_BUS=USB2"),
        "rpinas-pi4.env": ("RPINAS_BOARD=pi4", "RPINAS_SOC=BCM2711", "RPINAS_PRIMARY_STORAGE_BUS=USB3"),
        "rpinas-pi5.env": ("RPINAS_BOARD=pi5", "RPINAS_SOC=BCM2712", "RPINAS_PCIE=enabled"),
    }

    for filename, markers in expected.items():
        env_text = (REPO_ROOT / "rpi-image-gen" / filename).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in env_text


def test_image_workflow_verifies_non_empty_model_images_before_upload():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")

    assert 'dd if="$src" of="$output"' in workflow
    assert "Image is unexpectedly small" in workflow
    assert "fdisk -l" in workflow
    assert "xz -t" in workflow
    assert ".xz.sha256" in workflow


def test_image_workflow_uses_model_specific_emulated_cpus():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")

    assert "cpu: cortex-a7" in workflow
    assert "cpu_info: cpuinfo/raspberrypi_3b" in workflow
    assert "cpu: max:cortex-a72" in workflow
    assert "cpu_info: cpuinfo/raspberrypi_4b" in workflow
    assert "cpu: cortex-a76" in workflow
    assert "cpu_info: cpuinfo/raspberrypi_5" in workflow


def test_image_workflow_pins_runner_and_arm_runner_action_versions():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")

    assert "runs-on: ubuntu-24.04" in workflow
    assert "pguyot/arm-runner-action@v2.6.5" in workflow


def test_image_workflow_uploads_verified_artifact_directory():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")

    assert 'artifact_dir="dist/${{ matrix.model.artifact }}"' in workflow
    assert "path: dist/${{ matrix.model.artifact }}/" in workflow
    assert ".fdisk.txt" in workflow
