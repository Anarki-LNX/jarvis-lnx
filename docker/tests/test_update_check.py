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
ENV = {"HERMES_HOME": str(T), "NUORB_MODELS": str(T / "models"), "NUORB_CONTROL": str(T / "control")}
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


class UpdateAnfordern(unittest.TestCase):
    """„Jetzt aktualisieren“: Anforderung für die Hilfe auf dem Rechner (control/request/request.json)."""

    def setUp(self):
        import shutil
        shutil.rmtree(uc.CONTROL, ignore_errors=True)
        uc.cache_file().unlink(missing_ok=True)
        os.environ["NUORB_BUILD"] = "0.7.3"
        os.environ.pop("NUORB_UPDATE_CHECK", None)
        uc.transport, _ = antwort(body={"tag_name": "v0.7.4", "html_url": "https://github.com/Anarki-LNX/nuorb/releases/tag/v0.7.4"})
        asyncio.run(uc.fetch())

    def hilfe(self, status=None):
        (uc.CONTROL / "request").mkdir(parents=True)
        (uc.CONTROL / "status").mkdir(parents=True)
        (uc.CONTROL / "status" / "helper.json").write_text('{"variant":"docker","version":1,"auto_rollback":true}')
        if status:
            (uc.CONTROL / "status" / "status.json").write_text(json.dumps(status))

    def test_ohne_hilfe_kein_knopf_sondern_befehl(self):
        st = uc.state()
        self.assertIsNone(st["helper"])
        self.assertIn("install.sh", st["commands"]["update"])
        self.assertIn("--rollback", st["commands"]["rollback"])
        with self.assertRaises(PermissionError):
            uc.request_update("v0.7.4")

    def test_anforderung_hat_festes_format(self):
        self.hilfe()
        uc.request_update("v0.7.4")
        body = (uc.CONTROL / "request" / "request.json").read_text().strip()
        self.assertRegex(body, r'^\{"action":"update","release":"v0\.7\.4","id":"[a-f0-9]{32}"\}$')

    def test_nur_die_gefundene_neuere_version(self):
        self.hilfe()
        for v in ("v0.7.5", "v0.7.2", "v0.7.4; rm -rf /"):
            with self.assertRaises(ValueError, msg=v):
                uc.request_update(v)

    def test_nicht_waehrend_eines_laufs_und_hoechstens_alle_zehn_minuten(self):
        self.hilfe({"state": "running", "release": "v0.7.4", "time": "2026-11-28T12:00:00Z", "message": ""})
        with self.assertRaises(RuntimeError):
            uc.request_update("v0.7.4")
        (uc.CONTROL / "status" / "status.json").unlink()
        uc.request_update("v0.7.4")
        with self.assertRaises(RuntimeError):
            uc.request_update("v0.7.4")

    def test_offene_anforderung_bis_die_hilfe_antwortet(self):
        self.hilfe()
        st = uc.request_update("v0.7.4")
        self.assertEqual(st["pending"]["release"], "v0.7.4")   # sofort sichtbar, auch bevor die Hilfe läuft
        jetzt = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (uc.CONTROL / "status" / "status.json").write_text(json.dumps({"state": "running", "release": "v0.7.4", "time": jetzt}))
        self.assertIsNone(uc.state()["pending"])                # die Hilfe hat geantwortet

    def test_symlinks_werden_nicht_gelesen(self):
        self.hilfe()
        (uc.CONTROL / "status" / "helper.json").unlink()
        (uc.CONTROL / "status" / "helper.json").symlink_to("/etc/hostname")
        self.assertIsNone(uc.state()["helper"])


if __name__ == "__main__":
    unittest.main()
