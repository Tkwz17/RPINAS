import pytest

from backend import network


def _redirect_network_files(monkeypatch, tmp_path):
    hostapd_conf = tmp_path / "hostapd.conf"
    hostapd_default = tmp_path / "hostapd-default"
    dnsmasq_conf = tmp_path / "dnsmasq.d" / "rpinas.conf"
    monkeypatch.setattr(network, "HOSTAPD_CONF", str(hostapd_conf))
    monkeypatch.setattr(network, "HOSTAPD_DEFAULT", str(hostapd_default))
    monkeypatch.setattr(network, "DNSMASQ_CONF", str(dnsmasq_conf))
    return hostapd_conf, hostapd_default, dnsmasq_conf


def test_configure_access_point_defaults_to_open_network(monkeypatch, tmp_path):
    hostapd_conf, hostapd_default, dnsmasq_conf = _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")

    network.configure_access_point("RPINAS")

    hostapd = hostapd_conf.read_text(encoding="utf-8")
    assert "ssid=RPINAS" in hostapd
    assert "auth_algs=1" in hostapd
    assert "ignore_broadcast_ssid=0" in hostapd
    assert "hw_mode=g" in hostapd
    assert "channel=6" in hostapd
    assert "wpa=2" not in hostapd
    assert hostapd_default.read_text(encoding="utf-8") == f'DAEMON_CONF="{hostapd_conf}"\n'
    assert dnsmasq_conf.exists()


def test_configure_access_point_rejects_long_ssid(monkeypatch, tmp_path):
    _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")

    with pytest.raises(ValueError, match="1-32 bytes"):
        network.configure_access_point("é" * 17)


def test_configure_access_point_rejects_short_password(monkeypatch, tmp_path):
    _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")

    with pytest.raises(ValueError, match="8-63 bytes"):
        network.configure_access_point("RPINAS", "short")


def test_configure_access_point_writes_wpa_psk(monkeypatch, tmp_path):
    hostapd_conf, _, _ = _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")

    network.configure_access_point("RPINAS", "strong-pass")

    hostapd = hostapd_conf.read_text(encoding="utf-8")
    assert "wpa=2" in hostapd
    assert "wpa_psk=" in hostapd
    assert "wpa_passphrase=" not in hostapd


def test_configure_access_point_uses_env_ap_ip(monkeypatch, tmp_path):
    _, _, dnsmasq_conf = _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")
    monkeypatch.setenv("RPINAS_IP", "10.42.0.1")

    network.configure_access_point("RPINAS")

    dnsmasq = dnsmasq_conf.read_text(encoding="utf-8")
    assert "dhcp-range=10.42.0.10,10.42.0.200,255.255.255.0,24h" in dnsmasq
    assert "address=/#/10.42.0.1" in dnsmasq


def test_configure_access_point_rejects_invalid_env_ap_ip(monkeypatch, tmp_path):
    _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")
    monkeypatch.setenv("RPINAS_IP", "999.42.0.1")

    with pytest.raises(ValueError, match="octets"):
        network.configure_access_point("RPINAS")


def test_configure_access_point_defaults_country_to_us(monkeypatch, tmp_path):
    hostapd_conf, _, _ = _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")
    monkeypatch.delenv("RPINAS_COUNTRY", raising=False)

    network.configure_access_point("RPINAS")

    hostapd = hostapd_conf.read_text(encoding="utf-8")
    assert "country_code=US" in hostapd


def test_configure_access_point_uses_env_wifi_mode_and_channel(monkeypatch, tmp_path):
    hostapd_conf, _, _ = _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")
    monkeypatch.setenv("RPINAS_WIFI_HW_MODE", "a")
    monkeypatch.setenv("RPINAS_WIFI_CHANNEL", "36")

    network.configure_access_point("RPINAS")

    hostapd = hostapd_conf.read_text(encoding="utf-8")
    assert "hw_mode=a" in hostapd
    assert "channel=36" in hostapd


def test_configure_access_point_rejects_invalid_env_wifi_channel(monkeypatch, tmp_path):
    _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")
    monkeypatch.setenv("RPINAS_WIFI_CHANNEL", "0")

    with pytest.raises(ValueError, match="between 1 and 11"):
        network.configure_access_point("RPINAS")


def test_configure_access_point_rejects_non_us_country(monkeypatch, tmp_path):
    _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")
    monkeypatch.setenv("RPINAS_COUNTRY", "CA")

    with pytest.raises(ValueError, match="US operation only"):
        network.configure_access_point("RPINAS")


def test_configure_access_point_rejects_dfs_5ghz_channel_for_us(monkeypatch, tmp_path):
    _redirect_network_files(monkeypatch, tmp_path)
    monkeypatch.setattr(network, "resolve_wlan_iface", lambda timeout_seconds=5.0: "wlan0")
    monkeypatch.setenv("RPINAS_WIFI_HW_MODE", "a")
    monkeypatch.setenv("RPINAS_WIFI_CHANNEL", "52")

    with pytest.raises(ValueError, match="US 5GHz AP channel"):
        network.configure_access_point("RPINAS")


def test_resolve_wlan_iface_raises_when_no_wireless_interface(monkeypatch):
    monkeypatch.setattr(network, "WLAN_IFACE", "wlan-missing")
    monkeypatch.setattr(network, "_interface_exists", lambda name: False)
    monkeypatch.setattr(network, "detect_wireless_iface", lambda: None)

    with pytest.raises(RuntimeError, match="no wireless interface"):
        network.resolve_wlan_iface(timeout_seconds=0)


def test_validate_wifi_password_rejects_64_byte_multibyte_password():
    with pytest.raises(ValueError, match="8-63 bytes"):
        network.validate_wifi_password("é" * 32)


def test_validate_wifi_password_rejects_control_characters():
    with pytest.raises(ValueError, match="control characters"):
        network.validate_wifi_password("strong\npass")
