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

    network.configure_access_point("RPINAS")

    hostapd = hostapd_conf.read_text(encoding="utf-8")
    assert "ssid=RPINAS" in hostapd
    assert "auth_algs=1" in hostapd
    assert "ignore_broadcast_ssid=0" in hostapd
    assert "wpa=2" not in hostapd
    assert hostapd_default.read_text(encoding="utf-8") == f'DAEMON_CONF="{hostapd_conf}"\n'
    assert dnsmasq_conf.exists()


def test_configure_access_point_rejects_short_password(monkeypatch, tmp_path):
    _redirect_network_files(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="at least 8 characters"):
        network.configure_access_point("RPINAS", "short")


def test_configure_access_point_writes_wpa_psk(monkeypatch, tmp_path):
    hostapd_conf, _, _ = _redirect_network_files(monkeypatch, tmp_path)

    network.configure_access_point("RPINAS", "strong-pass")

    hostapd = hostapd_conf.read_text(encoding="utf-8")
    assert "wpa=2" in hostapd
    assert "wpa_psk=" in hostapd
    assert "wpa_passphrase=" not in hostapd
