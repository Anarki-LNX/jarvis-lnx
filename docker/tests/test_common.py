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
        for ip in ("192.168.1.60", ".".join(("10", "1", "2", "3")), "100.101.102.103", "127.0.0.1", "172.17.0.1", "fd00::5"):
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


class HeimCA(unittest.TestCase):
    """P2.10: Die Heim-CA gilt nur für Heimnetz-Namen, private IPs und die Namen aus NUORB_HOSTS."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ["NUORB_HOSTS"] = "192.168.1.50,nuorb.fritz.box,nuorb.example.org"
        os.environ["NUORB_TLS"] = "selfsigned"
        jc.ensure_certs()
        from cryptography import x509
        cls.x509 = x509
        cls.ca = x509.load_pem_x509_certificate((jc.CERTS / "nuorb-ca.crt").read_bytes())
        cls.leaf = x509.load_pem_x509_certificate((jc.CERTS / "server.crt").read_bytes())

    def pruefen(self, leaf, name):
        from cryptography.x509 import verification as v
        ziel = self.x509.IPAddress(__import__("ipaddress").ip_address(name)) if name[0].isdigit() else self.x509.DNSName(name)
        verifier = v.PolicyBuilder().store(v.Store([self.ca])).build_server_verifier(ziel)
        verifier.verify(leaf, [])

    def test_namensbeschraenkung_vorhanden_und_kritisch(self):
        ext = self.ca.extensions.get_extension_for_class(self.x509.NameConstraints)
        self.assertTrue(ext.critical)
        dns = [g.value for g in ext.value.permitted_subtrees if isinstance(g, self.x509.DNSName)]
        self.assertIn("local", dns)
        self.assertIn("nuorb.example.org", dns)
        self.assertNotIn("nuorb.fritz.box", dns, "schon durch fritz.box abgedeckt")

    def test_server_zertifikat_fuer_erlaubte_namen(self):
        for name in ("192.168.1.50", "nuorb.fritz.box", "nuorb.example.org"):
            with self.subTest(name=name):
                self.pruefen(self.leaf, name)

    def test_fremde_domain_mit_derselben_ca_wird_abgelehnt(self):
        import datetime as dt
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
        x509 = self.x509
        ca_key = serialization.load_pem_private_key((jc.CERTS / "nuorb-ca.key").read_bytes(), None)
        k = ec.generate_private_key(ec.SECP256R1())
        jetzt = dt.datetime.now(dt.timezone.utc)
        boese = (x509.CertificateBuilder()
                 .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "bank.example.com")]))
                 .issuer_name(self.ca.subject).public_key(k.public_key()).serial_number(x509.random_serial_number())
                 .not_valid_before(jetzt - dt.timedelta(minutes=1)).not_valid_after(jetzt + dt.timedelta(days=30))
                 .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                 .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                 .add_extension(x509.SubjectAlternativeName([x509.DNSName("bank.example.com")]), critical=False)
                 .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                 .sign(ca_key, hashes.SHA256()))
        from cryptography.x509.verification import VerificationError
        with self.assertRaises(VerificationError):
            self.pruefen(boese, "bank.example.com")

    def test_ca_covers(self):
        self.assertTrue(jc.ca_covers(self.ca, "nuorb.local"))
        self.assertTrue(jc.ca_covers(self.ca, "fd00::5"))
        self.assertFalse(jc.ca_covers(self.ca, "8.8.8.8"))
        self.assertFalse(jc.ca_covers(self.ca, "nuorb.example.com"))


if __name__ == "__main__":
    unittest.main()
