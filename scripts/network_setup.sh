#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/var/log/rpinas-network-setup.log"
mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'echo "RPINAS network setup failed (line ${LINENO}). Check ${LOG_FILE} and: journalctl -u hostapd -b --no-pager"' ERR

if [[ -f /etc/default/rpinas ]]; then
    # shellcheck disable=SC1091
    source /etc/default/rpinas
fi

# --- config (override via environment if needed) ---
RPINAS_SSID="${RPINAS_SSID:-RPINAS}"
RPINAS_IP="${RPINAS_IP:-192.168.4.1}"
RPINAS_COUNTRY="${RPINAS_COUNTRY:-US}"
RPINAS_PASSPHRASE="${RPINAS_PASSPHRASE:-}"
WLAN_IFACE="wlan0"

echo "[$(date --iso-8601=seconds)] Starting RPINAS network setup"

if [[ "${RPINAS_SSID}" =~ [[:cntrl:]] || ${#RPINAS_SSID} -eq 0 || $(printf %s "${RPINAS_SSID}" | wc -c) -gt 32 ]]; then
    echo "RPINAS_SSID must be 1-32 bytes with no control characters" >&2
    exit 1
fi

if [[ ! "${RPINAS_COUNTRY}" =~ ^[A-Z]{2}$ ]]; then
    echo "RPINAS_COUNTRY must be two uppercase ASCII letters" >&2
    exit 1
fi

if [[ ! "${RPINAS_IP}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    echo "RPINAS_IP must be an IPv4 address" >&2
    exit 1
fi
IFS=. read -r ip_octet_1 ip_octet_2 ip_octet_3 ip_octet_4 <<<"${RPINAS_IP}"
for octet in "${ip_octet_1}" "${ip_octet_2}" "${ip_octet_3}" "${ip_octet_4}"; do
    octet_value=$((10#$octet))
    if ((octet_value < 0 || octet_value > 255)); then
        echo "RPINAS_IP octets must be between 0 and 255" >&2
        exit 1
    fi
done

if [[ -n "${RPINAS_PASSPHRASE}" ]]; then
    passphrase_bytes=$(printf %s "${RPINAS_PASSPHRASE}" | wc -c)
    if [[ ${passphrase_bytes} -lt 8 || ${passphrase_bytes} -gt 63 || "${RPINAS_PASSPHRASE}" =~ [[:cntrl:]] ]]; then
        echo "RPINAS_PASSPHRASE must be empty for an open AP or 8-63 bytes without control characters for WPA2" >&2
        exit 1
    fi
fi

# --- make sure the radio is actually usable ---
rfkill unblock all || true
for _ in {1..10}; do
    if ! rfkill list 2>/dev/null | grep -q "Soft blocked: yes"; then
        break
    fi
    sleep 0.5
done

detect_wireless_iface() {
    iw dev 2>/dev/null | awk '/Interface/ { print $2; exit }'
}

resolve_wireless_iface() {
    if ip link show "${WLAN_IFACE}" >/dev/null 2>&1; then
        return 0
    fi

    local detected
    detected="$(detect_wireless_iface)"
    if [[ -n "${detected}" ]]; then
        WLAN_IFACE="${detected}"
        return 0
    fi
    return 1
}

for _ in {1..10}; do
    if resolve_wireless_iface; then
        break
    fi
    sleep 0.5
done

if ! resolve_wireless_iface; then
    echo "No wireless interface available after rfkill wait; AP cannot start."
    exit 1
fi
echo "Using wireless interface: ${WLAN_IFACE}"

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
if ! resolve_wireless_iface; then
    echo "Wireless interface disappeared before AP setup."
    exit 1
fi
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
ignore_broadcast_ssid=0
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
CFG
fi

chmod 600 /etc/hostapd/hostapd.conf

cat >/etc/default/hostapd <<CFG
DAEMON_CONF="/etc/hostapd/hostapd.conf"
CFG

mkdir -p /etc/systemd/system/hostapd.service.d
cat >/etc/systemd/system/hostapd.service.d/rpinas.conf <<'CFG'
[Unit]
StartLimitBurst=5
StartLimitIntervalSec=60

[Service]
Restart=on-failure
RestartSec=2
CFG
systemctl daemon-reload

# --- dnsmasq ---
DHCP_PREFIX="${ip_octet_1}.${ip_octet_2}.${ip_octet_3}"
cat >/etc/dnsmasq.d/rpinas.conf <<CFG
interface=${WLAN_IFACE}
bind-interfaces
dhcp-range=${DHCP_PREFIX}.10,${DHCP_PREFIX}.200,255.255.255.0,24h
address=/#/${RPINAS_IP}
CFG

systemctl unmask hostapd || true
for svc in hostapd dnsmasq; do
    started=0
    for attempt in 1 2 3; do
        if systemctl enable --now "${svc}" && systemctl is-active --quiet "${svc}"; then
            started=1
            break
        fi
        echo "Failed to start ${svc} (attempt ${attempt}/3), retrying..."
        sleep 2
    done
    if [[ "${started}" -ne 1 ]]; then
        echo "Failed to start ${svc} after retries."
        echo "Try: journalctl -u ${svc} -b --no-pager"
        exit 1
    fi
done

mkdir -p /var/lib/rpinas
touch /var/lib/rpinas/.network_configured
echo "[$(date --iso-8601=seconds)] RPINAS network setup complete"
