import hashlib
import os
import re
import subprocess
import time

HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"
DNSMASQ_CONF = "/etc/dnsmasq.d/rpinas.conf"
NM_UNMANAGED_CONF = "/etc/NetworkManager/conf.d/rpinas-unmanaged.conf"
WLAN_IFACE = "wlan0"
AP_IP = "192.168.4.1"
COUNTRY_CODE = os.environ.get("RPINAS_COUNTRY", "GB")

# 802.11 SSIDs are at most 32 bytes; disallow control characters (in
# particular newlines) so a crafted SSID can't inject extra directives
# into hostapd.conf.
SSID_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,32}$")


def _validate_ssid(ssid: str) -> str:
    if not SSID_PATTERN.fullmatch(ssid):
        raise ValueError("SSID must be 1-32 characters with no control characters")
    return ssid


def _service_exists(name: str) -> bool:
    result = subprocess.run(
        ["systemctl", "list-unit-files", name], capture_output=True, text=True, check=False
    )
    return name in result.stdout


def unblock_radio() -> None:
    subprocess.run(["rfkill", "unblock", "all"], check=False)


def release_interface_from_network_stack() -> None:
    """Make sure NetworkManager (Bookworm default) and dhcpcd (older images)
    both leave wlan0 alone, since hostapd needs exclusive control of it."""
    os.makedirs(os.path.dirname(NM_UNMANAGED_CONF), exist_ok=True)
    with open(NM_UNMANAGED_CONF, "w", encoding="utf-8") as f:
        f.write(f"[keyfile]\nunmanaged-devices=interface-name:{WLAN_IFACE}\n")

    if _service_exists("NetworkManager.service"):
        reloaded = subprocess.run(["systemctl", "reload", "NetworkManager"], check=False)
        if reloaded.returncode != 0:
            subprocess.run(["systemctl", "restart", "NetworkManager"], check=False)

    if _service_exists("dhcpcd.service"):
        try:
            content = open("/etc/dhcpcd.conf", "r", encoding="utf-8").read()
        except FileNotFoundError:
            content = ""
        if f"denyinterfaces {WLAN_IFACE}" not in content:
            with open("/etc/dhcpcd.conf", "a", encoding="utf-8") as f:
                f.write(f"\ndenyinterfaces {WLAN_IFACE}\n")
        subprocess.run(["systemctl", "restart", "dhcpcd"], check=False)


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

    hostapd = f"""interface={WLAN_IFACE}
driver=nl80211
country_code={COUNTRY_CODE}
ieee80211d=1
ssid={ssid}
hw_mode=g
channel={channel}
macaddr_acl=0
{wpa.strip()}\n"""

    dnsmasq = f"""interface={WLAN_IFACE}
bind-interfaces
dhcp-range=192.168.4.10,192.168.4.200,255.255.255.0,24h
address=/#/{AP_IP}
"""

    os.makedirs(os.path.dirname(DNSMASQ_CONF), exist_ok=True)
    os.makedirs(os.path.dirname(HOSTAPD_CONF), exist_ok=True)
    with open(HOSTAPD_CONF, "w", encoding="utf-8") as f:
        f.write(hostapd)
    os.chmod(HOSTAPD_CONF, 0o600)
    with open(DNSMASQ_CONF, "w", encoding="utf-8") as f:
        f.write(dnsmasq)


def apply_network_services() -> None:
    subprocess.run(["systemctl", "unmask", "hostapd"], check=False)
    subprocess.run(["systemctl", "enable", "hostapd", "dnsmasq"], check=False)
    # hostapd must claim the interface before dnsmasq binds to it.
    subprocess.run(["systemctl", "restart", "hostapd"], check=False)
    time.sleep(2)
    subprocess.run(["systemctl", "restart", "dnsmasq"], check=False)


def set_static_ap_address() -> None:
    """Bring wlan0 up with the AP's static IP directly. This does not rely
    on dhcpcd (absent on Bookworm/NetworkManager images) or on NetworkManager
    (which is told to ignore wlan0 in release_interface_from_network_stack)."""
    unblock_radio()
    release_interface_from_network_stack()
    subprocess.run(["ip", "link", "set", WLAN_IFACE, "down"], check=False)
    subprocess.run(["ip", "addr", "flush", "dev", WLAN_IFACE], check=False)
    subprocess.run(["ip", "link", "set", WLAN_IFACE, "up"], check=False)
    subprocess.run(["ip", "addr", "add", f"{AP_IP}/24", "dev", WLAN_IFACE], check=False)
