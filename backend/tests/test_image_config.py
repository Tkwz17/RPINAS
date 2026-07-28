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
        "rpinas-pi3.env": ("RPINAS_BOARD=pi3", "RPINAS_SOC=BCM2837", "RPINAS_PRIMARY_STORAGE_BUS=USB2", "RPINAS_COUNTRY=US"),
        "rpinas-pi4.env": ("RPINAS_BOARD=pi4", "RPINAS_SOC=BCM2711", "RPINAS_PRIMARY_STORAGE_BUS=USB3", "RPINAS_COUNTRY=US"),
        "rpinas-pi5.env": ("RPINAS_BOARD=pi5", "RPINAS_SOC=BCM2712", "RPINAS_PCIE=enabled", "RPINAS_COUNTRY=US"),
    }

    for filename, markers in expected.items():
        env_text = (REPO_ROOT / "rpi-image-gen" / filename).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in env_text


def test_image_packaging_script_verifies_non_empty_model_images_before_upload():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")
    packager = (REPO_ROOT / "ci/package-image.sh").read_text(encoding="utf-8")

    assert 'ci/package-image.sh "$src" "$output" "$min_bytes" "$artifact_dir"' in workflow
    assert 'dd if="$src" of="$output"' in packager
    assert "Image is unexpectedly small" in packager
    assert "fdisk -l" in packager
    assert "Artifact directory must contain exactly one .img file named" in packager


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
    packager = (REPO_ROOT / "ci/package-image.sh").read_text(encoding="utf-8")

    assert 'artifact_dir="dist/${{ matrix.model.artifact }}"' in workflow
    assert "path: dist/${{ matrix.model.artifact }}/" in workflow
    assert 'cp "$output" "$artifact_dir/$output"' in packager
    assert 'Output image must end in .img' in packager


def test_network_setup_validates_hostapd_byte_limits_and_decimal_ip_octets():
    script = (REPO_ROOT / "scripts" / "network_setup.sh").read_text(encoding="utf-8")

    assert "1-32 bytes" in script
    assert 'printf %s "${RPINAS_SSID}" | wc -c' in script
    assert "8-63 bytes" in script
    assert "octet_value=$((10#$octet))" in script


def test_image_installers_copy_hostapd_dropin():
    workflow = (REPO_ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")
    hook = (REPO_ROOT / "rpi-image-gen/build-hook.sh").read_text(encoding="utf-8")

    assert "systemd/hostapd.service.d/rpinas.conf" in workflow
    assert "systemd/hostapd.service.d/rpinas.conf" in hook


def test_image_packaging_verifies_boot_and_root_partitions_and_artifact_checksums():
    packager = (REPO_ROOT / "ci" / "package-image.sh").read_text(encoding="utf-8")

    assert "Disklabel type: dos" in packager
    assert "boot FAT32 and Linux root partitions" in packager
    assert "artifact immediately yields one flashable OS image file" in packager
    assert 'if [ ! -s "$artifact_dir/$output" ]; then' in packager
