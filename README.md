# RPINAS

RPINAS builds a Raspberry Pi OS Lite image that turns a Raspberry Pi into a small wireless NAS appliance. The image boots into a local WiFi access point, serves a Flask-based setup/admin UI, and configures Samba shares for NAS users.

## Current Status

This repository contains the application, runtime setup scripts, systemd units, and GitHub Actions image build workflow. It does **not** use upstream `rpi-image-gen` directly in CI; the workflow customizes official Raspberry Pi OS Lite images with `pguyot/arm-runner-action` and uploads artifacts that unzip to a single raw, flashable `.img` file.

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
- systemd units for network setup, Samba setup, first-boot initialization, the backend web UI, and an external GPIO status LED.

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
6. Enables RPINAS systemd services, including the status LED booting/ready units.
7. Copies the resulting raw `.img` into the artifact so downloading and unzipping the GitHub artifact yields a single flashable OS image file and nothing else.

Each workflow run should produce exactly three downloadable artifact ZIP files:

- `rpinas-raspberry-pi-3-bookworm-image.zip` -> contains only `rpinas-raspberry-pi-3-bookworm.img`
- `rpinas-raspberry-pi-4-bookworm-image.zip` -> contains only `rpinas-raspberry-pi-4-bookworm.img`
- `rpinas-raspberry-pi-5-bookworm-image.zip` -> contains only `rpinas-raspberry-pi-5-bookworm.img`

This repository intentionally does **not** commit generated image files.

## External Hook-Based Image Integration

If you are integrating with another image pipeline, use the provided hook and package list:

```bash
ROOTFS=/path/to/rootfs \
RPINAS_ENV_FILE=rpi-image-gen/rpinas-pi5.env \
./rpi-image-gen/build-hook.sh
```

The hook expects `ROOTFS` to point at a prepared Raspberry Pi OS root filesystem with the packages from `rpi-image-gen/packages/rpinas.list` already available or installable. `RPINAS_ENV_FILE` is required and must point to a model-specific env file (for example `rpi-image-gen/rpinas-pi3.env`, `rpi-image-gen/rpinas-pi4.env`, or `rpi-image-gen/rpinas-pi5.env`). The hook installs RPINAS into `/opt/rpinas`, copies the selected environment file to `/etc/default/rpinas`, and enables the RPINAS systemd units.

## First Boot Flow

1. Download the artifact ZIP for your hardware target:
   - Raspberry Pi 3 -> `rpinas-raspberry-pi-3-bookworm-image.zip`
   - Raspberry Pi 4 -> `rpinas-raspberry-pi-4-bookworm-image.zip`
   - Raspberry Pi 5 -> `rpinas-raspberry-pi-5-bookworm-image.zip`
2. Extract the ZIP once; you should get exactly one `.img` file for that model.
3. Flash that `.img` directly with Raspberry Pi Imager or Balena Etcher.
4. Boot the Pi.
5. The external status LED slow-blinks while startup services run.
6. The image configures `wlan0` as an AP using `/etc/default/rpinas` values (and falls back to the first `iw dev` interface if `wlan0` is absent).
7. Connect to the model-specific SSID.
8. Open `http://192.168.4.1`.
9. Complete setup and sign in to the admin dashboard.

## Status LED Wiring Guide

RPINAS images configure an optional 2-pin external status LED using the Raspberry Pi kernel `gpio-led` overlay. The default is GPIO17 (physical pin 11), active-high, exposed at `/sys/class/leds/rpinas-status`.

Runtime states:

| LED state | Meaning |
| --- | --- |
| Slow blink | Booting: RPINAS startup services are still initializing. |
| Solid on | Ready: AP/network services, Samba services, and the backend web UI are active and accepting connections. |
| Fast blink | Error: a critical startup service failed or readiness timed out. The error state remains visible until reboot or manual recovery. |

Wiring for the default active-high configuration:

1. Connect the LED anode (long leg, positive side) to a 220-330Ω series resistor.
2. Connect the other side of the resistor to Raspberry Pi GPIO17 (physical pin 11).
3. Connect the LED cathode (short leg, flat side) to any Raspberry Pi GND pin, such as physical pin 9.

Configuration defaults live in `/etc/default/rpinas`:

```bash
RPINAS_LED_ENABLED=1
RPINAS_LED_GPIO=17
RPINAS_LED_ACTIVE_LOW=0
RPINAS_LED_NAME=rpinas-status
```

To use a different GPIO on a deployed image, update both `/etc/default/rpinas` and the matching `dtoverlay=gpio-led,...` line in `/boot/firmware/config.txt` (or `/boot/config.txt` on older layouts), then reboot. For example, GPIO27 would use `RPINAS_LED_GPIO=27` and `dtoverlay=gpio-led,gpio=27,label=rpinas-status,active_low=0`. Set `RPINAS_LED_ENABLED=0` to disable LED state management.

Troubleshooting:

- LED never lights: confirm polarity, use a 220-330Ω resistor in series, verify the wire is on GPIO17/physical pin 11 (not pin 17), and check that `/sys/class/leds/rpinas-status` exists after boot.
- LED is inverted: set `active_low=1` in the boot overlay and `RPINAS_LED_ACTIVE_LOW=1`, or reverse an external transistor/driver circuit as appropriate.
- LED keeps fast-blinking: inspect failed startup services with `systemctl --failed` and logs such as `journalctl -u rpinas-network-setup -u hostapd -u dnsmasq -u rpinas-backend -b --no-pager`.
- LED slow-blinks indefinitely: check whether `hostapd`, `dnsmasq`, `smbd`, `nmbd`, or `rpinas-backend` is still starting or stuck.

## NAS File Structure

Default storage path: `/srv/rpinas/NAS`

- `/srv/rpinas/NAS/Shared`
- `/srv/rpinas/NAS/Users/<username>`

The admin password is only for the web dashboard. NAS access uses the Samba users created in setup or later in the Users page.

## Runtime Configuration Notes

- Network defaults come from `/etc/default/rpinas` and include `RPINAS_SSID`, `RPINAS_IP`, optional `RPINAS_PASSPHRASE`, `RPINAS_COUNTRY` (default `US`), plus optional AP radio tuning with `RPINAS_WIFI_HW_MODE` (`g` for 2.4GHz or `a` for 5GHz) and `RPINAS_WIFI_CHANNEL`.
- Status LED defaults also come from `/etc/default/rpinas`: `RPINAS_LED_ENABLED=1`, `RPINAS_LED_GPIO=17`, `RPINAS_LED_ACTIVE_LOW=0`, and `RPINAS_LED_NAME=rpinas-status`.
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

- AP setup defaults to `wlan0`, but falls back to the first wireless interface reported by `iw dev` when needed.
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
