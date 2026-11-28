"""Unit-Tests für docker/app/fetch_models.py (audit P1.3): feste Revision, Prüfsumme nach jedem Download."""
from __future__ import annotations

import functools
import hashlib
import http.server
import threading
import unittest

from _lade import APP, lade, temp_ordner

T = temp_ordner("models")
fm = lade("nuorb_fetch_models_test", APP / "fetch_models.py", {"HERMES_HOME": str(T / "data"), "NUORB_MODELS": str(T / "models")})
jc = fm.jc


class Server:
    """Kleiner HTTP-Server auf 127.0.0.1 für die Testdateien."""

    def __init__(self, ordner):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ordner))
        handler.log_message = lambda *a: None
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def stop(self):
        self.httpd.shutdown()


class Pruefsumme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quelle = temp_ordner("models-quelle")
        (cls.quelle / "echt.onnx").write_bytes(b"echte Modelldaten " * 1000)
        (cls.quelle / "boese.onnx").write_bytes(b"manipuliert " * 1000)
        cls.srv = Server(cls.quelle)
        cls.vorher = (fm.preflight, dict(fm.SHA256))
        fm.preflight = lambda url: None  # der Testserver lauscht nicht auf 443
        fm.SHA256["echt.onnx"] = hashlib.sha256((cls.quelle / "echt.onnx").read_bytes()).hexdigest()
        fm.SHA256["boese.onnx"] = fm.SHA256["echt.onnx"]  # erwartet die echten Daten, bekommt andere

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
        fm.preflight, fm.SHA256 = cls.vorher[0], cls.vorher[1]

    def test_passende_datei_wird_uebernommen(self):
        ziel = T / "echt.onnx"
        fm.fetch(f"{self.srv.url}/echt.onnx", ziel)
        self.assertEqual(ziel.read_bytes(), (self.quelle / "echt.onnx").read_bytes())

    def test_veraenderte_datei_wird_abgelehnt_und_geloescht(self):
        ziel = T / "boese.onnx"
        with self.assertRaises(fm.ChecksumError):
            fm.fetch(f"{self.srv.url}/boese.onnx", ziel)
        self.assertFalse(ziel.exists())
        self.assertFalse(ziel.with_name(ziel.name + ".part").exists())


class Quellen(unittest.TestCase):
    def test_feste_revision_statt_main(self):
        self.assertNotIn("/resolve/main", fm.HF)
        self.assertRegex(fm.HF_REV, r"^[0-9a-f]{40}$")

    def test_jede_waehlbare_stimme_hat_pruefsummen(self):
        for liste in jc.VOICE_CHOICES.values():
            for name, _ in liste:
                for ext in (".onnx", ".onnx.json"):
                    with self.subTest(datei=name + ext):
                        self.assertRegex(fm.SHA256.get(name + ext, ""), r"^[0-9a-f]{64}$")

    def test_parakeet_hat_pruefsumme(self):
        self.assertRegex(fm.SHA256.get(f"{fm.PARAKEET}.tar.bz2", ""), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
