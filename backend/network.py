import hashlib
import os
import re
import subprocess

HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"
DNSMASQ_CONF = "/etc/dnsmasq.d/rpinas.conf"
# 802.11 SSIDs are at most 32 bytes; disallow control characters (in
# particular newlines) so a crafted SSID can't inject extra directives
# into hostapd.conf.
SSID_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,32}$")


def _validate_ssid(ssid: str) -> str:
    if not SSID_PATTERN.fullmatch(ssid):
        raise ValueError("SSID must be 1-32 characters with no control characters")
    return ssid


def configure_access_point(ssid: str, password: str | None = None) -> None:
    ssid = _validate_ssid(ssid)
    channel = "6"
    if password:
        psk = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), ssid.encode("utf-8"), 4096, 32).hex()
        wpa = f"""
wpa=2
wpa_psk={psk}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
"""
    else:
        wpa = "auth_algs=1\nignore_broadcast_ssid=0\n"

    hostapd = f"""interface=wlan0
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
macaddr_acl=0
{wpa.strip()}\n"""

    dnsmasq = """interface=wlan0
dhcp-range=192.168.4.10,192.168.4.200,255.255.255.0,24h
address=/#/192.168.4.1
"""

    os.makedirs(os.path.dirname(DNSMASQ_CONF), exist_ok=True)
    with open(HOSTAPD_CONF, "w", encoding="utf-8") as f:
        f.write(hostapd)
    os.chmod(HOSTAPD_CONF, 0o600)
    with open(DNSMASQ_CONF, "w", encoding="utf-8") as f:
        f.write(dnsmasq)


def apply_network_services() -> None:
    subprocess.run(["systemctl", "enable", "hostapd", "dnsmasq"], check=False)
    subprocess.run(["systemctl", "restart", "hostapd", "dnsmasq"], check=False)


def set_static_ap_address() -> None:
    cfg = "/etc/dhcpcd.conf"
    block = "\ninterface wlan0\n    static ip_address=192.168.4.1/24\n    nohook wpa_supplicant\n"
    try:
        content = open(cfg, "r", encoding="utf-8").read()
    except FileNotFoundError:
        content = ""
    if "static ip_address=192.168.4.1/24" not in content:
        with open(cfg, "a", encoding="utf-8") as f:
            f.write(block)
