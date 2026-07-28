import hashlib
import os
import re
import subprocess
import sys
import time

HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"
HOSTAPD_DEFAULT = "/etc/default/hostapd"
DNSMASQ_CONF = "/etc/dnsmasq.d/rpinas.conf"
NM_UNMANAGED_CONF = "/etc/NetworkManager/conf.d/rpinas-unmanaged.conf"
WLAN_IFACE = "wlan0"
DEFAULT_AP_IP = "192.168.4.1"
DEFAULT_COUNTRY_CODE = "US"
DEFAULT_WIFI_HW_MODE = "g"
DEFAULT_WIFI_CHANNEL = "6"

# 802.11 SSIDs are at most 32 bytes; disallow control characters (in
# particular newlines) so a crafted SSID can't inject extra directives
# into hostapd.conf.
SSID_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]+$")
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
WIFI_HW_MODE_PATTERN = re.compile(r"^[ga]$")


def validate_ssid(ssid: str) -> str:
    if not SSID_PATTERN.fullmatch(ssid) or len(ssid.encode("utf-8")) > 32:
        raise ValueError("SSID must be 1-32 bytes with no control characters")
    return ssid


def _validate_ipv4_address(address: str) -> str:
    parts = address.split(".")
    if len(parts) != 4:
        raise ValueError("AP IP must be an IPv4 address")
    for part in parts:
        if not part.isdigit():
            raise ValueError("AP IP must be an IPv4 address")
        value = int(part, 10)
        if value < 0 or value > 255:
            raise ValueError("AP IP octets must be between 0 and 255")
    return address


def _validate_country_code(country_code: str) -> str:
    if not COUNTRY_PATTERN.fullmatch(country_code):
        raise ValueError("Country code must be two uppercase ASCII letters")
    return country_code


def _validate_wifi_hw_mode(hw_mode: str) -> str:
    if not WIFI_HW_MODE_PATTERN.fullmatch(hw_mode):
        raise ValueError("WiFi mode must be 'g' (2.4GHz) or 'a' (5GHz)")
    return hw_mode


def _validate_wifi_channel(channel: str) -> str:
    if not channel.isdigit():
        raise ValueError("WiFi channel must be a positive integer")
    channel_value = int(channel, 10)
    if channel_value < 1 or channel_value > 196:
        raise ValueError("WiFi channel must be between 1 and 196")
    return str(channel_value)


def _service_exists(name: str) -> bool:
    result = subprocess.run(
        ["systemctl", "list-unit-files", name], capture_output=True, text=True, check=False
    )
    return name in result.stdout


def _interface_exists(name: str) -> bool:
    return os.path.exists(f"/sys/class/net/{name}")


def detect_wireless_iface() -> str | None:
    try:
        result = subprocess.run(["iw", "dev"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    for line in result.stdout.splitlines():
        match = re.match(r"^\s*Interface\s+(\S+)$", line)
        if match:
            return match.group(1)
    return None


def resolve_wlan_iface(timeout_seconds: float = 5.0) -> str:
    global WLAN_IFACE
    if _interface_exists(WLAN_IFACE):
        return WLAN_IFACE

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        detected = detect_wireless_iface()
        if detected and _interface_exists(detected):
            WLAN_IFACE = detected
            return WLAN_IFACE
        time.sleep(0.5)

    print(
        f"RPINAS: no wireless interface found (expected {WLAN_IFACE}) after {timeout_seconds:.1f}s",
        file=sys.stderr,
    )
    return WLAN_IFACE


def unblock_radio() -> None:
    subprocess.run(["rfkill", "unblock", "all"], check=False)
    deadline = time.time() + 5
    while time.time() < deadline:
        rfkill_state = subprocess.run(["rfkill", "list"], capture_output=True, text=True, check=False)
        if "Soft blocked: yes" not in rfkill_state.stdout:
            break
        time.sleep(0.5)
    else:
        print("RPINAS: radio remains soft-blocked after rfkill unblock", file=sys.stderr)

    resolve_wlan_iface()


def release_interface_from_network_stack() -> None:
    """Make sure NetworkManager (Bookworm default) and dhcpcd (older images)
    both leave wlan0 alone, since hostapd needs exclusive control of it."""
    iface = resolve_wlan_iface()
    os.makedirs(os.path.dirname(NM_UNMANAGED_CONF), exist_ok=True)
    with open(NM_UNMANAGED_CONF, "w", encoding="utf-8") as f:
        f.write(f"[keyfile]\nunmanaged-devices=interface-name:{iface}\n")

    if _service_exists("NetworkManager.service"):
        reloaded = subprocess.run(["systemctl", "reload", "NetworkManager"], check=False)
        if reloaded.returncode != 0:
            subprocess.run(["systemctl", "restart", "NetworkManager"], check=False)

    if _service_exists("dhcpcd.service"):
        try:
            content = open("/etc/dhcpcd.conf", "r", encoding="utf-8").read()
        except FileNotFoundError:
            content = ""
        if f"denyinterfaces {iface}" not in content:
            with open("/etc/dhcpcd.conf", "a", encoding="utf-8") as f:
                f.write(f"\ndenyinterfaces {iface}\n")
        subprocess.run(["systemctl", "restart", "dhcpcd"], check=False)


def configure_access_point(ssid: str, password: str | None = None) -> None:
    iface = resolve_wlan_iface()
    ssid = validate_ssid(ssid)
    hw_mode = _validate_wifi_hw_mode(os.environ.get("RPINAS_WIFI_HW_MODE", DEFAULT_WIFI_HW_MODE))
    channel = _validate_wifi_channel(os.environ.get("RPINAS_WIFI_CHANNEL", DEFAULT_WIFI_CHANNEL))
    if password and len(password) < 8:
        raise ValueError("WiFi password must be empty or at least 8 characters")
    if password:
        psk = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), ssid.encode("utf-8"), 4096, 32).hex()
        wpa = f"""
wpa=2
wpa_psk={psk}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
"""
    else:
        wpa = "auth_algs=1\n"

    hostapd = f"""interface={iface}
driver=nl80211
country_code={_validate_country_code(os.environ.get("RPINAS_COUNTRY", DEFAULT_COUNTRY_CODE))}
ieee80211d=1
ssid={ssid}
hw_mode={hw_mode}
channel={channel}
macaddr_acl=0
ignore_broadcast_ssid=0
{wpa.strip()}\n"""

    ap_ip = _validate_ipv4_address(os.environ.get("RPINAS_IP", DEFAULT_AP_IP))
    dhcp_prefix = ".".join(ap_ip.split(".")[:3])
    dnsmasq = f"""interface={iface}
bind-interfaces
dhcp-range={dhcp_prefix}.10,{dhcp_prefix}.200,255.255.255.0,24h
address=/#/{ap_ip}
"""

    os.makedirs(os.path.dirname(DNSMASQ_CONF), exist_ok=True)
    os.makedirs(os.path.dirname(HOSTAPD_CONF), exist_ok=True)
    with open(HOSTAPD_CONF, "w", encoding="utf-8") as f:
        f.write(hostapd)
    os.chmod(HOSTAPD_CONF, 0o600)
    with open(HOSTAPD_DEFAULT, "w", encoding="utf-8") as f:
        f.write(f'DAEMON_CONF="{HOSTAPD_CONF}"\n')
    with open(DNSMASQ_CONF, "w", encoding="utf-8") as f:
        f.write(dnsmasq)


def apply_network_services() -> None:
    subprocess.run(["systemctl", "unmask", "hostapd"], check=False)
    subprocess.run(["systemctl", "enable", "hostapd", "dnsmasq"], check=True)
    # hostapd must claim the interface before dnsmasq binds to it.
    for attempt in range(1, 4):
        restarted = subprocess.run(["systemctl", "restart", "hostapd"], check=False)
        active = subprocess.run(["systemctl", "is-active", "--quiet", "hostapd"], check=False)
        if restarted.returncode == 0 and active.returncode == 0:
            break
        if attempt == 3:
            raise subprocess.CalledProcessError(
                active.returncode or restarted.returncode, ["systemctl", "restart", "hostapd"]
            )
        time.sleep(2)
    time.sleep(2)
    subprocess.run(["systemctl", "restart", "dnsmasq"], check=True)
    subprocess.run(["systemctl", "is-active", "--quiet", "dnsmasq"], check=True)


def set_static_ap_address() -> None:
    """Bring wlan0 up with the AP's static IP directly. This does not rely
    on dhcpcd (absent on Bookworm/NetworkManager images) or on NetworkManager
    (which is told to ignore wlan0 in release_interface_from_network_stack)."""
    unblock_radio()
    release_interface_from_network_stack()
    iface = resolve_wlan_iface()
    subprocess.run(["ip", "link", "set", iface, "down"], check=False)
    subprocess.run(["ip", "addr", "flush", "dev", iface], check=False)
    subprocess.run(["ip", "link", "set", iface, "up"], check=False)
    ap_ip = _validate_ipv4_address(os.environ.get("RPINAS_IP", DEFAULT_AP_IP))
    subprocess.run(["ip", "addr", "add", f"{ap_ip}/24", "dev", iface], check=False)
