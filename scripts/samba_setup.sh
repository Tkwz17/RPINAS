#!/usr/bin/env bash
set -euo pipefail

mkdir -p /srv/rpinas/NAS/Shared /srv/rpinas/NAS/Users
chmod 777 /srv/rpinas/NAS/Shared

cat >/etc/samba/smb.conf <<'CFG'
[global]
   workgroup = WORKGROUP
   server string = RPINAS
   map to guest = Bad User
   guest account = nobody
   security = user
   passdb backend = tdbsam

[Shared]
   path = /srv/rpinas/NAS/Shared
   browseable = yes
   writable = yes
   guest ok = yes
   guest only = yes
   force user = nobody
   create mask = 0666
   directory mask = 0777
CFG

systemctl enable smbd nmbd
systemctl restart smbd nmbd

mkdir -p /var/lib/rpinas
touch /var/lib/rpinas/.samba_configured
