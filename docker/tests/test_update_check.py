"""Update-Prüfung im Admin-Panel (v0.7.3): Versionsvergleich, Cache, Fehler, Abschalten. GitHub wird nie gefragt,
die Antwort kommt aus einem httpx.MockTransport."""
from __future__ import annotations

import asyncio
import json
import os
import time
import unittest

import httpx

from _lade import APP, lade, temp_ordner

T = temp_ordner("update")
ENV = {"HERMES_HOME": str(T), "NUORB_MODELS": str(T / "models")}
jc = lade("nuorb_common", APP / "nuorb_common.py", ENV)   # Name wie im Image: update_check importiert nuorb_common
uc = lade("update_check_test", APP / "update_check.py", ENV)


def antwort(status=200, body=None):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(status, json=body if body is not None else {})
    return httpx.MockTransport(handler), calls


class UpdatePruefung(unittest.TestCase):
    def setUp(self):
        uc.cache_file().unlink(missing_ok=True)
        os.environ["NUORB_BUILD"] = "0.7.3"
        os.environ.pop("NUORB_UPDATE_CHECK", None)

    def holen(self, status=200, body=None):
        uc.transport, calls = antwort(status, body)
        asyncio.run(uc.fetch())
        return calls

    def test_versionen(self):
        self.assertEqual(jc.version_tuple("v0.7.10"), (0, 7, 10))
        self.assertIsNone(jc.version_tuple("dev"))
        self.assertIsNone(jc.version_tuple("v0.8.0-rc1"))

    def test_neuere_version_mit_link(self):
        calls = self.holen(body={"tag_name": "v0.7.4", "html_url": "https://github.com/Anarki-LNX/nuorb/releases/tag/v0.7.4",
                                 "published_at": "2026-12-01T10:00:00Z"})
        self.assertEqual(calls, [uc.UPDATE_URL])
        st = uc.state()
        self.assertTrue(st["newer"])
        self.assertEqual(st["latest"], "v0.7.4")
        self.assertTrue(st["url"].startswith(uc.NOTES_PREFIX))

    def test_gleiche_oder_aeltere_version_ist_kein_update(self):
        for tag in ("v0.7.3", "v0.7.2"):
            uc.cache_file().unlink(missing_ok=True)
            self.holen(body={"tag_name": tag, "html_url": "https://github.com/Anarki-LNX/nuorb/releases/tag/" + tag})
            self.assertFalse(uc.state()["newer"], tag)

    def test_dev_bau_zeigt_kein_update(self):
        os.environ["NUORB_BUILD"] = "dev"
        self.holen(body={"tag_name": "v9.9.9"})
        self.assertFalse(uc.state()["newer"])

    def test_fremder_link_wird_verworfen(self):
        self.holen(body={"tag_name": "v0.7.4", "html_url": "https://boese.example/nuorb"})
        self.assertIsNone(uc.state()["url"])

    def test_fehler_wird_gespeichert_nicht_geworfen(self):
        self.holen(status=403, body={"message": "rate limit"})
        st = uc.state()
        self.assertTrue(st["error"])
        self.assertFalse(st["newer"])

    def test_hoechstens_einmal_pro_minute(self):
        self.holen(body={"tag_name": "v0.7.4"})
        calls = self.holen(body={"tag_name": "v0.7.5"})
        self.assertEqual(calls, [])
        self.assertEqual(uc.state()["latest"], "v0.7.4")

    def test_automatisch_alle_sechs_stunden_und_abschaltbar(self):
        self.assertTrue(uc.due())                       # noch nie geprüft
        self.holen(body={"tag_name": "v0.7.4"})
        self.assertFalse(uc.due())                      # gerade geprüft
        c = json.loads(uc.cache_file().read_text())
        c["t"] = time.time() - uc.EVERY - 1
        uc.cache_file().write_text(json.dumps(c))
        self.assertTrue(uc.due())
        uc.set_auto(False)
        self.assertFalse(uc.due())
        uc.set_auto(True)
        os.environ["NUORB_UPDATE_CHECK"] = "0"
        self.assertFalse(uc.due())
        self.assertFalse(uc.state()["enabled"])


if __name__ == "__main__":
    unittest.main()
