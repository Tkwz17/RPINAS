# RPINAS

RPINAS is a Raspberry Pi NAS appliance project that builds a ready-to-flash system image (via `rpi-image-gen`) for a wireless NAS experience with first-boot setup and browser-based management.

## Features

- First-boot automatic WiFi access point
  - Default SSID: `RPINAS`
  - Default mode: open network (no password)
  - Default admin IP: `192.168.4.1`
- Setup wizard at `http://192.168.4.1`
  - Create immutable admin dashboard password
  - Create at least one NAS user
  - Enable/disable guest access for `Shared`
  - Select NAS storage path/device mount
- Samba-based NAS shares for Windows/macOS/Linux
  - `NAS/Shared` read/write for all NAS users
  - `NAS/Users/<username>` private per user
- Admin panel pages
  - Dashboard
  - Users
  - Storage
  - Network
  - System
- systemd services for boot orchestration
- rpi-image-gen integration files (packages + build hook)

## Supported Raspberry Pi Models

- Raspberry Pi 3B+ (`RPINAS-Pi3`, 32-bit armhf, low-memory profile, USB 2.0 throughput expectations)
- Raspberry Pi 4 (`RPINAS-Pi4`, 64-bit arm64, balanced profile, USB 3.0 storage support)
- Raspberry Pi 5 (`RPINAS-Pi5`, 64-bit arm64, performance profile, USB 3.0 plus optional PCIe/NVMe storage support)

The GitHub Actions image workflow produces one artifact per model so each image carries defaults that match what that Raspberry Pi can and cannot do. Any other model with a supported Linux image, onboard/compatible WiFi, and enough storage may work with a custom environment file.

## Repository Layout

- `/backend` - Flask backend + static frontend UI
- `/scripts` - runtime configuration scripts
- `/systemd` - service units
- `/rpi-image-gen` - image build integration files

## Image Build Requirements

- Linux host with `rpi-image-gen`
- Internet access for package installation during build
- Raspberry Pi base image configuration compatible with custom rootfs hooks

## Build Instructions

1. Install and configure `rpi-image-gen` in your build environment.
2. Include package list from:
   - `rpi-image-gen/packages/rpinas.list`
3. Choose a model-specific environment file, or keep the balanced default:
   - `rpi-image-gen/rpinas-pi3.env`
   - `rpi-image-gen/rpinas-pi4.env`
   - `rpi-image-gen/rpinas-pi5.env`
   - `rpi-image-gen/rpinas.env` (default Pi 4 balanced profile)
4. Register and run custom hook:
   - `RPINAS_ENV_FILE=/path/to/env rpi-image-gen/build-hook.sh`
5. Build image with your normal `rpi-image-gen` pipeline.
6. Flash output image using Raspberry Pi Imager.
7. Insert SD card in Pi and boot.

> This repository intentionally does **not** generate or commit the final `.img` file.


## Image Validation

Before flashing a release image, run the repository checks that validate the backend and image integration scripts:

```bash
pytest -q
python -m compileall -q backend
bash -n scripts/*.sh rpi-image-gen/build-hook.sh
```

To smoke-test the image hook without producing a final `.img`, run it against an already-prepared `rpi-image-gen` root filesystem that contains the packages from `rpi-image-gen/packages/rpinas.list`:

```bash
ROOTFS=/path/to/rpi-image-gen/rootfs RPINAS_ENV_FILE=rpi-image-gen/rpinas-pi5.env ./rpi-image-gen/build-hook.sh
```

The hook installs RPINAS into `/opt/rpinas`, copies the selected environment to `/etc/default/rpinas`, and enables the first-boot, network, Samba, and backend systemd units. After flashing, confirm the first boot by connecting to the image-specific WiFi network, such as `RPINAS-Pi3`, `RPINAS-Pi4`, or `RPINAS-Pi5`, and opening `http://192.168.4.1`.

## First Boot Flow

1. Pi boots and runs first-boot service.
2. RPINAS configures AP/network services and Samba base config.
3. Connect a client device to the model-specific WiFi SSID, such as `RPINAS-Pi3`, `RPINAS-Pi4`, or `RPINAS-Pi5`.
4. Open `http://192.168.4.1`.
5. Complete setup wizard.
6. Sign in to admin dashboard.

## NAS File Structure

Default storage path: `/srv/rpinas/NAS`

- `/srv/rpinas/NAS/Shared`
- `/srv/rpinas/NAS/Users/<username>`

The admin account is management-only and is not a NAS share user.

## User Management

- Add user
- Remove user
- Reset user password
- Toggle guest access to Shared folder

Guest access never grants private user folder access.

## Storage Setup

- Detects block devices via `lsblk`
- Allows moving NAS path to selected mount path
- Applies Samba config to updated storage location

## Network Setup

- Change SSID
- Add/update WiFi password
- AP changes return `reboot_required=true`

## System Actions

- Reboot
- Shutdown
- Backend log view (`journalctl`)

## Security Notes

- Admin password and NAS user passwords are hashed in backend DB
- Admin password is set during setup and not exposed for web change
- Session cookie is HttpOnly

## Known Limitations

- Static admin IP `192.168.4.1` depends on AP mode and local radio/driver behavior.
- Some USB devices may require manual mounting policy in base image.
- Samba user creation requires root/system privileges.

## Future Improvements

- TLS for admin panel
- Multi-disk management and RAID support
- Better SMB session analytics
- Background jobs for long-running storage migrations
- Optional OTA update workflow

## rpi-image-gen Integration Details

The `rpi-image-gen` directory contains the files needed to include RPINAS in an image build:

- `rpi-image-gen/packages/rpinas.list` - packages that must be installed in the image.
- `rpi-image-gen/build-hook.sh` - custom hook that copies RPINAS files into the target rootfs, installs the backend, and enables RPINAS services.
- `rpi-image-gen/rpinas.env` - default Pi 4 balanced image configuration values.
- `rpi-image-gen/rpinas-pi3.env`, `rpi-image-gen/rpinas-pi4.env`, and `rpi-image-gen/rpinas-pi5.env` - model-specific image defaults used by CI.

Expected integration flow:

1. Include `rpi-image-gen/packages/rpinas.list` in the image package manifest.
2. Set `RPINAS_ENV_FILE` to the model-specific defaults you want baked into the image.
3. Run `rpi-image-gen/build-hook.sh` as a custom hook after packages are installed and before image finalization.
4. Build with the normal `rpi-image-gen` workflow.

The repository GitHub Actions workflow runs the same install path three times: a Raspberry Pi 3 armhf/low-memory image, a Raspberry Pi 4 arm64/balanced image, and a Raspberry Pi 5 arm64/performance image.
