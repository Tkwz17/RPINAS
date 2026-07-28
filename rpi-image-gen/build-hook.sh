#!/usr/bin/env bash
set -euo pipefail

ROOTFS="${ROOTFS:?ROOTFS must be set by rpi-image-gen}"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RPINAS_ENV_FILE="${RPINAS_ENV_FILE:?RPINAS_ENV_FILE must be set to a model-specific env file (for example rpi-image-gen/rpinas-pi3.env)}"

if [[ ! -f "$RPINAS_ENV_FILE" ]]; then
    echo "RPINAS env file not found: $RPINAS_ENV_FILE" >&2
    exit 1
fi

install -d "$ROOTFS/opt/rpinas-src" "$ROOTFS/usr/local/bin" "$ROOTFS/etc/systemd/system" \
    "$ROOTFS/etc/systemd/system/hostapd.service.d" "$ROOTFS/etc/default"
rm -rf "$ROOTFS/opt/rpinas-src/backend"
cp -a "$SRC_DIR/backend" "$ROOTFS/opt/rpinas-src/backend"

install -m 0755 "$SRC_DIR/scripts/first_boot.sh" "$ROOTFS/usr/local/bin/rpinas-first-boot"
install -m 0755 "$SRC_DIR/scripts/network_setup.sh" "$ROOTFS/usr/local/bin/rpinas-network-setup"
install -m 0755 "$SRC_DIR/scripts/samba_setup.sh" "$ROOTFS/usr/local/bin/rpinas-samba-setup"
install -m 0755 "$SRC_DIR/scripts/install_backend.sh" "$ROOTFS/usr/local/bin/rpinas-install-backend"
install -m 0644 "$RPINAS_ENV_FILE" "$ROOTFS/etc/default/rpinas"

install -m 0644 "$SRC_DIR/systemd/rpinas-backend.service" "$ROOTFS/etc/systemd/system/rpinas-backend.service"
install -m 0644 "$SRC_DIR/systemd/rpinas-firstboot.service" "$ROOTFS/etc/systemd/system/rpinas-firstboot.service"
install -m 0644 "$SRC_DIR/systemd/rpinas-network-setup.service" "$ROOTFS/etc/systemd/system/rpinas-network-setup.service"
install -m 0644 "$SRC_DIR/systemd/rpinas-samba-setup.service" "$ROOTFS/etc/systemd/system/rpinas-samba-setup.service"
install -m 0644 "$SRC_DIR/systemd/hostapd.service.d/rpinas.conf" \
    "$ROOTFS/etc/systemd/system/hostapd.service.d/rpinas.conf"
chroot "$ROOTFS" /usr/local/bin/rpinas-install-backend
chroot "$ROOTFS" systemctl enable rpinas-firstboot.service rpinas-network-setup.service rpinas-samba-setup.service rpinas-backend.service
