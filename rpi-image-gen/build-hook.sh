#!/usr/bin/env bash
set -euo pipefail

ROOTFS="${ROOTFS:?ROOTFS must be set by rpi-image-gen}"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

install -d "$ROOTFS/opt/rpinas-src" "$ROOTFS/usr/local/bin" "$ROOTFS/etc/systemd/system"
cp -r "$SRC_DIR/backend" "$ROOTFS/opt/rpinas-src/backend"

install -m 0755 "$SRC_DIR/scripts/first_boot.sh" "$ROOTFS/usr/local/bin/rpinas-first-boot"
install -m 0755 "$SRC_DIR/scripts/network_setup.sh" "$ROOTFS/usr/local/bin/rpinas-network-setup"
install -m 0755 "$SRC_DIR/scripts/samba_setup.sh" "$ROOTFS/usr/local/bin/rpinas-samba-setup"
install -m 0755 "$SRC_DIR/scripts/install_backend.sh" "$ROOTFS/usr/local/bin/rpinas-install-backend"

install -m 0644 "$SRC_DIR/systemd/rpinas-backend.service" "$ROOTFS/etc/systemd/system/rpinas-backend.service"
install -m 0644 "$SRC_DIR/systemd/rpinas-firstboot.service" "$ROOTFS/etc/systemd/system/rpinas-firstboot.service"
install -m 0644 "$SRC_DIR/systemd/rpinas-network-setup.service" "$ROOTFS/etc/systemd/system/rpinas-network-setup.service"
install -m 0644 "$SRC_DIR/systemd/rpinas-samba-setup.service" "$ROOTFS/etc/systemd/system/rpinas-samba-setup.service"
install -m 0644 "$SRC_DIR/systemd/rpinas-nas-management.service" "$ROOTFS/etc/systemd/system/rpinas-nas-management.service"

chroot "$ROOTFS" /usr/local/bin/rpinas-install-backend
chroot "$ROOTFS" systemctl enable rpinas-firstboot.service rpinas-network-setup.service rpinas-samba-setup.service rpinas-backend.service rpinas-nas-management.service
