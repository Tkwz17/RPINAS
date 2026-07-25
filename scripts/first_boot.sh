#!/usr/bin/env bash
set -euo pipefail

mkdir -p /var/lib/rpinas
mkdir -p /srv/rpinas/NAS/Shared /srv/rpinas/NAS/Users
chmod 777 /srv/rpinas/NAS/Shared

# Network + Samba setup are handled by their own dedicated systemd services
# (rpinas-network-setup.service / rpinas-samba-setup.service), which this
# unit now explicitly depends on via Requires=/After=. Do NOT invoke them
# directly here as well - doing so caused both paths to race and rewrite
# hostapd.conf/smb.conf and restart services concurrently.


touch /var/lib/rpinas/.first_boot_done
