#!/usr/bin/env bash
set -euo pipefail

# --- config (override via environment if needed) ---
RPINAS_SSID="${RPINAS_SSID:-RPINAS}"
RPINAS_IP="${RPINAS_IP:-192.168.4.1}"
RPINAS_COUNTRY="${RPINAS_COUNTRY:-GB}"
RPINAS_PASSPHRASE="${RPINAS_PASSPHRASE:-}"
WLAN_IFACE="wlan0"

if [[ -n "${RPINAS_PASSPHRASE}" && ${#RPINAS_PASSPHRASE} -lt 8 ]]; then
    echo "RPINAS_PASSPHRASE must be empty for an open AP or at least 8 characters for WPA2" >&2
    exit 1
fi

# --- make sure the radio is actually usable ---
rfkill unblock all || true

# --- stop NetworkManager (or dhcpcd, if present) from fighting hostapd for wlan0 ---
mkdir -p /etc/NetworkManager/conf.d
cat >/etc/NetworkManager/conf.d/rpinas-unmanaged.conf <<CFG
[keyfile]
unmanaged-devices=interface-name:${WLAN_IFACE}
CFG

if systemctl list-unit-files | grep -q '^NetworkManager.service'; then
    systemctl reload NetworkManager 2>/dev/null || systemctl restart NetworkManager || true
fi

if systemctl list-unit-files | grep -q '^dhcpcd.service'; then
    # Belt-and-braces: if dhcpcd is present on this image, keep it off wlan0 too.
    if ! grep -q "^denyinterfaces ${WLAN_IFACE}" /etc/dhcpcd.conf 2>/dev/null; then
        echo "denyinterfaces ${WLAN_IFACE}" >> /etc/dhcpcd.conf
    fi
    systemctl restart dhcpcd || true
fi

# --- bring the interface up with a static IP ourselves ---
ip link set "${WLAN_IFACE}" down || true
ip addr flush dev "${WLAN_IFACE}"
ip link set "${WLAN_IFACE}" up
ip addr add "${RPINAS_IP}/24" dev "${WLAN_IFACE}"

# --- hostapd ---
mkdir -p /etc/hostapd /etc/dnsmasq.d
cat >/etc/hostapd/hostapd.conf <<CFG
interface=${WLAN_IFACE}
driver=nl80211
country_code=${RPINAS_COUNTRY}
ieee80211d=1
ssid=${RPINAS_SSID}
hw_mode=g
channel=6
macaddr_acl=0
CFG

if [[ -n "${RPINAS_PASSPHRASE}" ]]; then
    cat >>/etc/hostapd/hostapd.conf <<CFG
wpa=2
wpa_passphrase=${RPINAS_PASSPHRASE}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
CFG
else
    cat >>/etc/hostapd/hostapd.conf <<CFG
auth_algs=1
ignore_broadcast_ssid=0
CFG
fi

chmod 600 /etc/hostapd/hostapd.conf

cat >/etc/default/hostapd <<CFG
DAEMON_CONF="/etc/hostapd/hostapd.conf"
CFG

# --- dnsmasq ---
cat >/etc/dnsmasq.d/rpinas.conf <<CFG
interface=${WLAN_IFACE}
bind-interfaces
dhcp-range=192.168.4.10,192.168.4.200,255.255.255.0,24h
address=/#/${RPINAS_IP}
CFG

systemctl unmask hostapd || true
systemctl enable hostapd dnsmasq

# Restart in the right order: hostapd needs to claim the interface before dnsmasq binds to it.
systemctl restart hostapd
sleep 2
systemctl restart dnsmasq

mkdir -p /var/lib/rpinas
touch /var/lib/rpinas/.network_configured
