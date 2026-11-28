"""Unit-Tests für die Oberfläche (docker/src/ui/server.py): CSRF-Schutz für schreibende /api/*-Anfragen
(die 13 Fälle aus der Prüfung vom 27.11.2026) und die Kopplungspflicht."""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from _lade import SRC, lade, temp_ordner

T = temp_ordner("ui")
ui = lade("nuorb_ui_test", SRC / "ui/server.py", {
    "NUORB_MODE": "demo", "NUORB_REQUIRE_PAIRING": "0", "UI_ALLOWED_ORIGINS": "https://nuorb.example:8443",
    "NUORB_CONF_DIR": str(T), "HOME": str(T), "NUORB_ALLOWED_HOSTS": "nuorb.example.org,*.ts.net", "UI_CONFIG": str(T / "ui.json"), "UI_CERT_DIR": str(T / "certs"),
})
BASE = "https://192.168.1.50:8443"
J, TXT = "application/json", "text/plain"


def anfrage(method="POST", path="/api/ask", ct=J, **h):
    c = TestClient(ui.app, base_url=BASE, client=("192.168.1.60", 50000))
    hdr = {"Content-Type": ct, **{k.replace("_", "-"): v for k, v in h.items()}}
    return c.request(method, path, headers=hdr, content=b'{"text":""}' if method == "POST" else None)


class Csrf(unittest.TestCase):
    def gesperrt(self, r):
        self.assertEqual(r.status_code, 403, r.text)

    def durch(self, r):
        self.assertNotEqual(r.status_code, 403, r.text)

    def test_fremde_seite_text_plain(self):
        self.gesperrt(anfrage(ct=TXT, Origin="https://boese.example"))

    def test_fremde_seite_cross_site(self):
        self.gesperrt(anfrage(Origin="https://boese.example", Sec_Fetch_Site="cross-site"))

    def test_origin_null(self):
        self.gesperrt(anfrage(ct=TXT, Origin="null"))

    def test_gleiche_ip_anderer_port(self):
        self.gesperrt(anfrage(Origin="https://192.168.1.50:8444", Sec_Fetch_Site="same-site"))

    def test_nur_sec_fetch_site_cross_site(self):
        self.gesperrt(anfrage(Sec_Fetch_Site="cross-site"))

    def test_http_statt_https(self):
        self.gesperrt(anfrage(Origin="http://192.168.1.50:8443"))

    def test_eigene_oberflaeche(self):
        self.durch(anfrage(Origin=BASE, Sec_Fetch_Site="same-origin"))

    def test_eigene_oberflaeche_ohne_sec_fetch(self):
        self.durch(anfrage(Origin=BASE))

    def test_app_kiosk_curl_ohne_origin(self):
        self.durch(anfrage())

    def test_zusaetzlich_erlaubte_herkunft(self):
        self.durch(anfrage(Origin="https://nuorb.example:8443", Sec_Fetch_Site="cross-site"))

    def test_get_von_fremder_seite_unberuehrt(self):
        self.durch(anfrage("GET", "/api/info", Origin="https://boese.example"))

    def test_kopplung_von_fremder_seite(self):
        self.gesperrt(anfrage(path="/api/pair", ct=TXT, Origin="https://boese.example"))

    def test_bearer_mit_fremdem_origin(self):
        self.durch(anfrage(Origin="https://appassets.androidplatform.net", Authorization="Bearer x"))


class Kopplungspflicht(unittest.TestCase):
    def setUp(self):
        self.vorher = ui.pairing_required
        ui.pairing_required = lambda: True

    def tearDown(self):
        ui.pairing_required = self.vorher

    def test_ohne_geraet_401(self):
        self.assertEqual(anfrage("GET", "/api/status").status_code, 401)

    def test_info_bleibt_offen(self):
        r = anfrage("GET", "/api/info")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("product"), "nuorb")

    def test_falscher_token_401(self):
        self.assertEqual(anfrage("GET", "/api/status", Authorization="Bearer falsch").status_code, 401)


class HostAllowlist(unittest.TestCase):
    """P1.5: DNS-Rebinding. Fremde Hostnamen werden abgelehnt, die Formen aus dem Heimnetz gehen durch."""
    ERLAUBT = ["192.168.1.50:{p}", "192.168.1.50", "[fe80::1]:{p}", "[::1]", "localhost:{p}", "nuorb:{p}", "nuorb.local:{p}",
               "nuorb.fritz.box", "nuorb.home.arpa", "nuorb.lan:{p}", "nuorb.example.org:{p}", "geraet.tail1234.ts.net"]
    VERBOTEN = ["boese.example:{p}", "nuorb.example.org.boese.example", "192.168.1.50.nip.io", "example.org", "ts.net.boese.example"]

    def test_hosts(self):
        for h in self.ERLAUBT:
            with self.subTest(host=h):
                self.assertNotEqual(host_anfrage(h.format(p=8443)).status_code, 421)
        for h in self.VERBOTEN:
            with self.subTest(host=h):
                self.assertEqual(host_anfrage(h.format(p=8443)).status_code, 421)


def host_anfrage(host):
    return TestClient(ui.app, base_url=BASE, client=("192.168.1.60", 1)).get("/api/info", headers={"Host": host})


if __name__ == "__main__":
    unittest.main()
