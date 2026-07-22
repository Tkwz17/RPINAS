#!/usr/bin/env bash
set -euo pipefail

cat >/etc/dhcpcd.conf <<'CFG'
hostname
clientid
persistent
option rapid_commit
option domain_name_servers, domain_name, domain_search, host_name
option classless_static_routes
option interface_mtu
require dhcp_server_identifier
slaac private

interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
CFG

mkdir -p /etc/hostapd /etc/dnsmasq.d
cat >/etc/hostapd/hostapd.conf <<'CFG'
interface=wlan0
driver=nl80211
ssid=RPINAS
hw_mode=g
channel=6
auth_algs=1
ignore_broadcast_ssid=0
CFG

cat >/etc/default/hostapd <<'CFG'
DAEMON_CONF="/etc/hostapd/hostapd.conf"
CFG

cat >/etc/dnsmasq.d/rpinas.conf <<'CFG'
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.200,255.255.255.0,24h
address=/#/192.168.4.1
CFG

systemctl unmask hostapd || true
systemctl enable hostapd dnsmasq
systemctl restart hostapd dnsmasq

mkdir -p /var/lib/rpinas
touch /var/lib/rpinas/.network_configured
