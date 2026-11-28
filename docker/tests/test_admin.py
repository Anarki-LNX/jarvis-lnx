"""Unit-Tests für das Admin-Panel (docker/src/admin/server.py): Einrichtung, Anmeldung, Sperre, CSRF, Cookies,
Vorschau mit Sicherung und Rückgängig, Pfadprüfungen, Schwärzung."""
from __future__ import annotations

import json
import stat
import unittest

from fastapi.testclient import TestClient

from _lade import SRC, lade, temp_ordner

T = temp_ordner("admin")
adm = lade("nuorb_admin_test", SRC / "admin/server.py", {
    "NUORB_HOME": str(T), "ADMIN_DATA": str(T / "data"), "HERMES_HOME": str(T / "hermes"),
    "HERMES_BIN": str(T / "fehlt/hermes"), "NUORB_UI_SETTINGS": str(T / "ui.json"), "ADMIN_CTL_DIR": str(T / "ctl"),
    "ADMIN_CERTS": str(T / "certs"), "NUORB_UI_STATIC": str(T / "static"),
})
BASE = "https://192.168.1.50:8444"
PW = "Test-Passwort-sicher-42"


def client(ip: str = "192.168.1.60", **h) -> TestClient:
    c = TestClient(adm.app, base_url=BASE, client=(ip, 50000))
    c.headers.update({"X-NuOrb": "1", "Origin": BASE, **h})
    return c


def einrichten() -> None:
    if not adm.auth_configured():
        adm.ensure_setup_code()
        code = adm.SETUP_FILE.read_text().strip()
        r = client("192.168.1.61").post("/api/auth/setup", json={"code": code, "password": PW})
        assert r.status_code == 200, r.text


def angemeldet(ip: str = "192.168.1.62") -> TestClient:
    einrichten()
    c = client(ip)
    r = c.post("/api/auth/login", json={"password": PW})
    assert r.status_code == 200, r.text
    return c


class A0Einrichtung(unittest.TestCase):  # vor allen anderen Klassen (unittest sortiert nach Namen)
    def test_1_setup_code_nur_fuer_den_besitzer_lesbar(self):
        if adm.auth_configured():
            self.skipTest("schon eingerichtet")
        adm.ensure_setup_code()
        self.assertEqual(stat.S_IMODE(adm.SETUP_FILE.stat().st_mode), 0o600)

    def test_2_falscher_code_wird_abgelehnt(self):
        if adm.auth_configured():
            self.skipTest("schon eingerichtet")
        adm.ensure_setup_code()
        r = client("192.168.1.70").post("/api/auth/setup", json={"code": "AAAA-BBBB-CCCC", "password": PW})
        self.assertEqual(r.status_code, 403)

    def test_3_richtiger_code_setzt_passwort_und_loescht_code(self):
        einrichten()
        self.assertTrue(adm.auth_configured())
        self.assertFalse(adm.SETUP_FILE.exists())
        self.assertEqual(stat.S_IMODE(adm.AUTH_FILE.stat().st_mode), 0o600)
        self.assertEqual(json.loads(adm.AUTH_FILE.read_text())["alg"], "scrypt")
        self.assertNotIn(PW, adm.AUTH_FILE.read_text())

    def test_4_zweite_einrichtung_geht_nicht(self):
        einrichten()
        r = client("192.168.1.71").post("/api/auth/setup", json={"code": "egal", "password": PW})
        self.assertEqual(r.status_code, 409)


class Anmeldung(unittest.TestCase):
    def test_falsches_passwort(self):
        einrichten()
        self.assertEqual(client("192.168.1.80").post("/api/auth/login", json={"password": "falsch-falsch"}).status_code, 403)

    def test_sperre_nach_fuenf_fehlversuchen(self):
        einrichten()
        c = client("192.168.1.81")
        codes = [c.post("/api/auth/login", json={"password": f"falsch-{i}"}).status_code for i in range(6)]
        self.assertEqual(codes[:5], [403] * 5)
        self.assertEqual(codes[5], 429)
        # auch das richtige Passwort kommt während der Sperre nicht durch
        self.assertEqual(c.post("/api/auth/login", json={"password": PW}).status_code, 429)

    def test_sperre_gilt_pro_adresse(self):
        einrichten()
        self.assertEqual(client("192.168.1.82").post("/api/auth/login", json={"password": PW}).status_code, 200)

    def test_sitzungscookie_ist_geschuetzt(self):
        einrichten()
        r = client("192.168.1.83").post("/api/auth/login", json={"password": PW})
        sc = r.headers.get("set-cookie", "").lower()
        for teil in ("nuorb_sess=", "httponly", "secure", "samesite=strict"):
            self.assertIn(teil, sc)
        self.assertFalse(any(r.cookies["nuorb_sess"] in json.dumps(v) or r.cookies["nuorb_sess"] in k
                             for k, v in adm.SESSIONS.items()), "Sitzung nur als Hash gespeichert")

    def test_ohne_anmeldung_gesperrt(self):
        self.assertEqual(client("192.168.1.84").get("/api/backups").status_code, 401)

    def test_abmelden(self):
        c = angemeldet("192.168.1.85")
        self.assertEqual(c.get("/api/backups").status_code, 200)
        c.post("/api/auth/logout")
        self.assertEqual(c.get("/api/backups").status_code, 401)


class CsrfUndNetz(unittest.TestCase):
    def test_ohne_eigenen_header_abgelehnt(self):
        c = TestClient(adm.app, base_url=BASE, client=("192.168.1.90", 1))
        self.assertEqual(c.post("/api/auth/login", json={"password": PW}, headers={"Origin": BASE}).status_code, 403)

    def test_fremder_origin_abgelehnt(self):
        c = client("192.168.1.91", Origin="https://boese.example")
        self.assertEqual(c.post("/api/auth/login", json={"password": PW}).status_code, 403)

    def test_text_plain_von_fremder_seite_abgelehnt(self):
        c = TestClient(adm.app, base_url=BASE, client=("192.168.1.92", 1))
        r = c.post("/api/auth/login", content=b'{"password":"x"}',
                   headers={"Origin": "https://boese.example", "Content-Type": "text/plain"})
        self.assertEqual(r.status_code, 403)

    def test_nur_heimnetz(self):
        c = TestClient(adm.app, base_url=BASE, client=("203.0.113.5", 1))
        self.assertEqual(c.get("/api/auth/state").status_code, 403)

    def test_internal_nur_loopback(self):
        c = TestClient(adm.app, base_url=BASE, client=("192.168.1.93", 1))
        self.assertEqual(c.post("/internal/brain", json={}, headers={"X-NuOrb-Internal": "x"}).status_code, 403)

    def test_internal_ohne_token_auch_von_loopback_abgelehnt(self):
        c = TestClient(adm.app, base_url=BASE, client=("127.0.0.1", 1))
        self.assertEqual(c.post("/internal/brain", json={}, headers={"X-NuOrb-Internal": "falsch"}).status_code, 403)

    def test_sicherheitskoepfe(self):
        r = client("192.168.1.94").get("/api/auth/state")
        self.assertIn("script-src 'self'", r.headers.get("content-security-policy", ""))
        self.assertEqual(r.headers.get("x-frame-options"), "DENY")


class AenderungenMitSicherung(unittest.TestCase):
    SKILL = "skill:nuorb-test/demo"
    TEXT = "---\nname: demo\ndescription: Testskill\n---\nErster Stand\n"

    def test_vorschau_anwenden_und_rueckgaengig(self):
        c = angemeldet("192.168.1.100")
        p = adm.make_preview(self.SKILL, self.TEXT, "Test anlegen")
        self.assertIn("+Erster Stand", p["diff"])
        r = c.post(f"/api/change/{p['preview']}/apply")
        self.assertEqual(r.status_code, 200, r.text)
        pfad, _ = adm.file_path(self.SKILL)
        self.assertEqual(pfad.read_text(), self.TEXT)
        bid = r.json()["backup"]
        # zweite Änderung, dann die Sicherung der ersten zurückholen (Rückgängig)
        p2 = adm.make_preview(self.SKILL, self.TEXT.replace("Erster", "Zweiter"), "Test ändern")
        self.assertEqual(c.post(f"/api/change/{p2['preview']}/apply").status_code, 200)
        r = c.post(f"/api/backups/{bid}/restore")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.post(f"/api/change/{r.json()['preview']}/apply").status_code, 200)
        self.assertFalse(pfad.exists(), "Rückgängig auf den Stand vor dem Anlegen löscht den Skill wieder")

    def test_vorschau_verfaellt_nach_gebrauch(self):
        c = angemeldet("192.168.1.101")
        p = adm.make_preview("skill:nuorb-test/einmal", self.TEXT, "einmal")
        self.assertEqual(c.post(f"/api/change/{p['preview']}/apply").status_code, 200)
        self.assertEqual(c.post(f"/api/change/{p['preview']}/apply").status_code, 410)

    def test_zwischendurch_geaenderte_datei_wird_nicht_ueberschrieben(self):
        c = angemeldet("192.168.1.102")
        key = "skill:nuorb-test/konflikt"
        p = adm.make_preview(key, self.TEXT, "anlegen")
        pfad, _ = adm.file_path(key)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text("von Hermes geändert\n")
        self.assertEqual(c.post(f"/api/change/{p['preview']}/apply").status_code, 409)
        self.assertEqual(pfad.read_text(), "von Hermes geändert\n")

    def test_ungueltiger_skill_wird_abgelehnt(self):
        with self.assertRaises(adm.HTTPException):
            adm.make_preview("skill:nuorb-test/kaputt", "kein Kopf\n", "kaputt")


class Pfadpruefungen(unittest.TestCase):
    def test_unbekannte_datei(self):
        for key in ("../../etc/passwd", "skill:../x", "skill:a/../../b", "skill:A/B", "skill:/abs", ""):
            with self.subTest(key=key), self.assertRaises(adm.HTTPException):
                adm.file_path(key)

    def test_sicherung_mit_pfadanteil(self):
        c = angemeldet("192.168.1.110")
        for bid in ("..", "..%2F..%2Fetc", "gibt-es-nicht"):
            with self.subTest(bid=bid):
                self.assertIn(c.post(f"/api/backups/{bid}/restore").status_code, (404, 405))


class Schwaerzung(unittest.TestCase):
    def test_schluessel_werden_verborgen(self):
        for geheim in ("sk-ant-api03-" + "x" * 40, "Bearer " + "a" * 40):
            with self.subTest(geheim=geheim[:12]):
                self.assertNotIn(geheim[-20:], adm.redact_text(f"Wert: {geheim} Ende"))

    def test_baum_mit_geheimen_schluesseln(self):
        out = adm.redact_tree({"api_key": "geheim1234567890", "name": "sichtbar", "liste": [{"token": "abcdefgh12345678"}]})
        self.assertEqual(out["name"], "sichtbar")
        self.assertNotEqual(out["api_key"], "geheim1234567890")
        self.assertNotEqual(out["liste"][0]["token"], "abcdefgh12345678")


if __name__ == "__main__":
    unittest.main()
