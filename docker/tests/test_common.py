"""Unit-Tests für docker/app/nuorb_common.py: Kopplungscodes, Geräte-Token, Widerruf, Dateirechte."""
from __future__ import annotations

import stat
import time
import unittest

from _lade import APP, lade, temp_ordner

T = temp_ordner("common")
jc = lade("nuorb_common_test", APP / "nuorb_common.py", {"HERMES_HOME": str(T), "NUORB_MODELS": str(T / "models")})


class Kopplung(unittest.TestCase):
    def neuer_code(self) -> str:
        return jc.new_pairing_code("test")["code"]

    def test_code_einmalig(self):
        code = self.neuer_code()
        self.assertTrue(jc.redeem_pairing_code(code))
        self.assertFalse(jc.redeem_pairing_code(code))

    def test_falscher_code(self):
        self.assertFalse(jc.redeem_pairing_code("AAAA-AAAA"))
        self.assertFalse(jc.redeem_pairing_code(""))

    def test_abgelaufener_code(self):
        code = self.neuer_code()
        data = jc._read_json(jc.PAIRING, {})
        for v in data.values():
            v["exp"] = time.time() - 1
        jc._write_json(jc.PAIRING, data)
        self.assertFalse(jc.redeem_pairing_code(code))

    def test_dateien_nur_fuer_den_besitzer(self):
        self.neuer_code()
        jc.add_device("Test", "android", "192.168.1.60")
        for p in (jc.PAIRING, jc.DEVICES):
            with self.subTest(p=p.name):
                self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)


class Geraete(unittest.TestCase):
    def test_token_gilt_und_wird_nur_als_hash_gespeichert(self):
        did, token = jc.add_device("Handy", "android", "192.168.1.61")
        self.assertEqual(jc.device_for_token(token, "192.168.1.61"), did)
        self.assertNotIn(token, jc.DEVICES.read_text())

    def test_widerruf(self):
        did, token = jc.add_device("Weg", "android", "192.168.1.62")
        self.assertTrue(jc.revoke_device(did))
        self.assertIsNone(jc.device_for_token(token))
        self.assertFalse(jc.revoke_device(did))

    def test_unsinnige_token(self):
        self.assertIsNone(jc.device_for_token(""))
        self.assertIsNone(jc.device_for_token("x" * 500))
        self.assertIsNone(jc.device_for_token("falsch"))


class Sperren(unittest.TestCase):
    """P1.7: Lesen, Ändern und Schreiben von devices.json und pairing.json als ein Schritt."""

    def test_widerruf_wird_nicht_von_last_seen_ueberschrieben(self):
        import threading
        did, token = jc.add_device("Rennen", "android", "192.168.1.70")
        jc._seen_cache.pop(did, None)

        def widerruf_langsam():  # wie die Verwaltung: lesen, kurz warten, ohne das Gerät schreiben
            with jc.json_lock(jc.DEVICES):
                d = jc.devices()
                time.sleep(0.3)
                d.pop(did)
                jc._write_json(jc.DEVICES, d)
        t = threading.Thread(target=widerruf_langsam)
        t.start()
        time.sleep(0.05)
        ergebnis = jc.device_for_token(token, "192.168.1.70")  # will last_seen schreiben
        t.join()
        self.assertNotIn(did, jc.devices(), "widerrufenes Gerät ist wieder da")
        self.assertIsNone(ergebnis)

    def test_code_bei_gleichzeitigen_anfragen_nur_einmal(self):
        from concurrent.futures import ThreadPoolExecutor
        code = jc.new_pairing_code("test")["code"]
        with ThreadPoolExecutor(10) as ex:
            treffer = list(ex.map(lambda _: jc.redeem_pairing_code(code), range(10)))
        self.assertEqual(treffer.count(True), 1, treffer)

    def test_sperrdatei_nur_fuer_den_besitzer(self):
        jc.add_device("Rechte", "android", "192.168.1.71")
        lock = jc.DEVICES.with_name(jc.DEVICES.name + ".lock")
        self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)


class NetzUndProxy(unittest.TestCase):
    """P1.6: Allowlist ohne das ganze 172.16.0.0/12, eigener Docker-Gateway erlaubt, Proxy-Köpfe nur auf Wunsch."""

    def setUp(self):
        import os
        self.os = os
        self.vorher = (jc.default_gateway, os.environ.pop("NUORB_ALLOWED_NETS", None), os.environ.pop("NUORB_TRUSTED_PROXY", None))
        jc.default_gateway = lambda route_file="/proc/net/route": "172.17.0.1"

    def tearDown(self):
        jc.default_gateway = self.vorher[0]
        for k, v in (("NUORB_ALLOWED_NETS", self.vorher[1]), ("NUORB_TRUSTED_PROXY", self.vorher[2])):
            self.os.environ.pop(k, None)
            if v is not None:
                self.os.environ[k] = v

    def erlaubt(self, ip):
        import ipaddress
        return any(ipaddress.ip_address(ip) in n for n in jc.allowed_nets())

    def test_standard(self):
        for ip in ("192.168.1.60", "10.1.2.3", "100.101.102.103", "127.0.0.1", "172.17.0.1", "fd00::5"):
            with self.subTest(ip=ip):
                self.assertTrue(self.erlaubt(ip))
        for ip in ("172.18.0.7", "172.20.0.5", "8.8.8.8", "203.0.113.5"):
            with self.subTest(ip=ip):
                self.assertFalse(self.erlaubt(ip))

    def test_eigene_liste_ersetzt_den_standard(self):
        self.os.environ["NUORB_ALLOWED_NETS"] = "172.20.0.0/16"
        self.assertTrue(self.erlaubt("172.20.0.5"))
        self.assertFalse(self.erlaubt("192.168.1.60"))

    def test_gateway_aus_routentabelle(self):
        f = T / "route"
        f.write_text("Iface\tDestination\tGateway\teth0\nx\t0000FEA9\t00000000\neth0\t00000000\t010011AC\n")
        self.assertEqual(self.vorher[0](str(f)), "172.17.0.1")
        self.assertIsNone(self.vorher[0](str(T / "fehlt")))

    def test_proxy_koepfe_nur_mit_vertrauenswuerdigem_proxy(self):
        self.assertEqual(jc.proxy_kwargs(), {"proxy_headers": False})
        self.os.environ["NUORB_TRUSTED_PROXY"] = "192.168.1.2"
        self.assertEqual(jc.proxy_kwargs(), {"proxy_headers": True, "forwarded_allow_ips": "192.168.1.2"})


if __name__ == "__main__":
    unittest.main()
