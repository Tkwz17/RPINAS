#!/usr/bin/env bash
set -euo pipefail

mkdir -p /var/lib/rpinas
mkdir -p /srv/rpinas/NAS/Shared /srv/rpinas/NAS/Users
chmod 777 /srv/rpinas/NAS/Shared

/usr/local/bin/rpinas-network-setup
/usr/local/bin/rpinas-samba-setup
systemctl enable rpinas-backend.service
systemctl start rpinas-backend.service

touch /var/lib/rpinas/.first_boot_done
