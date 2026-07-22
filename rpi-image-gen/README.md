# RPINAS rpi-image-gen Integration

This directory contains the files required to integrate RPINAS into an `rpi-image-gen` build pipeline.

## Contents

- `packages/rpinas.list`: packages that must be installed in the image.
- `build-hook.sh`: hook that copies RPINAS files into rootfs and enables services.
- `rpinas.env`: default image configuration values.

## Expected usage

1. Include `packages/rpinas.list` in your image package manifest.
2. Run `build-hook.sh` as a custom hook after packages are installed and before image finalization.
3. Build with your normal `rpi-image-gen` workflow.
