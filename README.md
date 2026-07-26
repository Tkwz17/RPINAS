# RPINAS

RPINAS builds a Raspberry Pi OS Lite image that turns a Raspberry Pi into a small wireless NAS appliance. The image boots into a local WiFi access point, serves a Flask-based setup/admin UI, and configures Samba shares for NAS users.

## Current Status

This repository contains the application, runtime setup scripts, systemd units, and GitHub Actions image build workflow. It does **not** use upstream `rpi-image-gen` directly in CI; the workflow customizes official Raspberry Pi OS Lite images with `pguyot/arm-runner-action` and uploads artifacts that unzip to a raw, flashable `.img` file, with a verified `.img.xz` copy and SHA-256 checksums.

## What the Image Provides

- Model-specific Raspberry Pi OS Lite image artifacts for Pi 3, Pi 4, and Pi 5.
- First-boot WiFi access point for setup.
  - Default admin URL: `http://192.168.4.1`
  - Default AP is open unless `RPINAS_PASSPHRASE` is set in the image environment.
  - Default SSIDs are model-specific: `RPINAS-Pi3`, `RPINAS-Pi4`, or `RPINAS-Pi5`.
- Browser setup wizard to:
  - Set the admin dashboard password.
  - Create at least one NAS/Samba user.
  - Enable or disable guest access to `Shared`.
  - Use SD-card storage or the first mounted external storage device.
- Admin dashboard pages for status, users, storage, network, system actions, and logs.
- Samba shares:
  - `Shared` at `<storage>/Shared`.
  - Per-user private shares at `<storage>/Users/<username>`.
- systemd units for network setup, Samba setup, first-boot initialization, and the backend web UI.

## Supported Raspberry Pi Targets

| Target | Architecture | Default SSID | Profile | Storage notes |
| --- | --- | --- | --- | --- |
| Raspberry Pi 3 | armhf / BCM2837 / 32-bit boot | `RPINAS-Pi3` | low-memory | Minimal GPU memory, Bluetooth disabled, USB 2.0 storage/network limits expected. |
| Raspberry Pi 4 | arm64 / BCM2711 / 64-bit boot | `RPINAS-Pi4` | balanced | Minimal GPU memory, Bluetooth disabled, USB 3.0 storage support. |
| Raspberry Pi 5 | arm64 / BCM2712 / 64-bit boot | `RPINAS-Pi5` | performance | Minimal GPU memory, PCIe enabled for NVMe/HAT storage, USB 3.0 support. |

Other Raspberry Pi models may work if the base OS has compatible WiFi, enough storage, and suitable package support, but only the targets above are represented in the included workflow matrix.

## Repository Layout

- `backend/` - Flask API, static frontend, persistence helpers, Samba/network/storage logic, and tests.
- `scripts/` - image/runtime installation and first-boot setup scripts.
- `systemd/` - services installed into the image.
- `rpi-image-gen/` - package list, image hook, and model environment defaults. These files are useful for external image-builder integration even though CI currently uses `arm-runner-action` directly.
- `.github/workflows/build-image.yml` - GitHub Actions image build workflow.

## Building Images with GitHub Actions

The included workflow runs on pushes to `main` or `MAIN`, and can also be started manually with **workflow_dispatch**.

For each model, the workflow:

1. Boots a Raspberry Pi OS Lite base image under `pguyot/arm-runner-action`.
2. Installs packages listed in `rpi-image-gen/packages/rpinas.list`.
3. Copies the backend, setup scripts, selected model environment file, and systemd units into the image.
4. Appends model-specific boot tuning to the image boot config, such as Pi 3 32-bit mode, Pi 4 64-bit headless tuning, or Pi 5 PCIe enablement for NVMe/HAT storage.
5. Runs `rpinas-install-backend` inside the image to create `/opt/rpinas/.venv` and install backend Python dependencies.
6. Enables RPINAS systemd services.
7. Copies the resulting raw `.img` into the artifact so downloading and unzipping the GitHub artifact yields a flashable OS image file, then also creates and verifies a matching `.img.xz` copy and SHA-256 checksums.

This repository intentionally does **not** commit generated image files.

## External Hook-Based Image Integration

If you are integrating with another image pipeline, use the provided hook and package list:

```bash
ROOTFS=/path/to/rootfs \
RPINAS_ENV_FILE=rpi-image-gen/rpinas-pi5.env \
./rpi-image-gen/build-hook.sh
```

The hook expects `ROOTFS` to point at a prepared Raspberry Pi OS root filesystem with the packages from `rpi-image-gen/packages/rpinas.list` already available or installable. It installs RPINAS into `/opt/rpinas`, copies the selected environment file to `/etc/default/rpinas`, and enables the RPINAS systemd units.

## First Boot Flow

1. Download and unzip a generated GitHub Actions artifact, then flash the raw `.img` file inside it with Raspberry Pi Imager or another imaging tool. The artifact also includes a verified `.img.xz` copy for tools that prefer compressed images.
2. Boot the Pi.
3. The image configures `wlan0` as an AP using `/etc/default/rpinas` values.
4. Connect to the model-specific SSID.
5. Open `http://192.168.4.1`.
6. Complete setup and sign in to the admin dashboard.

## NAS File Structure

Default storage path: `/srv/rpinas/NAS`

- `/srv/rpinas/NAS/Shared`
- `/srv/rpinas/NAS/Users/<username>`

The admin password is only for the web dashboard. NAS access uses the Samba users created in setup or later in the Users page.

## Runtime Configuration Notes

- Network defaults come from `/etc/default/rpinas` and include `RPINAS_SSID`, `RPINAS_IP`, optional `RPINAS_PASSPHRASE`, and `RPINAS_COUNTRY`.
- NAS usernames must be Linux/Samba-compatible: start with a lowercase letter or underscore, then use lowercase letters, numbers, underscores, or hyphens; maximum length is 32 characters.
- Backend-driven network changes update hostapd/dnsmasq configuration and return `reboot_required=true`.
- Samba configuration is regenerated when setup completes, users change, guest access changes, or storage target changes.
- External storage selection uses mounted non-SD block devices detected with `lsblk`.
- System actions include reboot, shutdown, and recent backend log viewing via `journalctl` with an audit-log fallback.

## Local Validation

Run these checks before opening a PR or flashing a test image:

```bash
pytest -q
python -m compileall -q backend
bash -n scripts/*.sh rpi-image-gen/build-hook.sh
```

## Security Notes

- Admin and NAS user passwords are stored as hashes in the backend database.
- Samba passwords are passed to `smbpasswd` via stdin rather than through shell interpolation.
- Session cookies are HttpOnly and SameSite=Strict.
- The default AP is open unless you bake in `RPINAS_PASSPHRASE`; use a passphrase for untrusted environments.
- The web UI currently serves HTTP, not HTTPS.

## Known Limitations

- The appliance assumes `wlan0` is the AP-capable wireless interface.
- AP reliability depends on Raspberry Pi model, regulatory country, firmware, and local radio conditions.
- External storage must already be mounted for automatic selection.
- Samba user and service management require root privileges on the Pi.
- The admin password cannot currently be changed from the web UI after setup.

## Future Improvements

- HTTPS support for the admin panel.
- Multi-disk management and RAID options.
- More explicit external-drive mounting workflows.
- Background jobs for long-running storage migrations.
- Optional update/upgrade workflow for deployed appliances.
