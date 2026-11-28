"""Unit-Tests für docker/app/weather_admin.py (Verwaltungsseite „Wetter“): Ortssuche nur über den Namen, Speichern,
Schlüssel nur maskiert,
Prüfung der Eingaben, Test-Knopf. Wetterdienste gemockt, keine echten Abfragen. Anmeldung und CSRF macht der Wächter
des Admin-Panels (test_admin.py), hier wird nur die Logik der Routen geprüft."""
from __future__ import annotations

import json
import stat
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from _lade import APP, lade, temp_ordner

T = temp_ordner("weather-admin")
ENV = {"HERMES_HOME": str(T), "NUORB_CONF": str(T / "conf"), "NUORB_WEATHER_CACHE": str(T / "cache")}
nw = lade("nuorb_weather", APP / "nuorb_weather.py", ENV)
wa = lade("weather_admin_test", APP / "weather_admin.py", ENV)
wa.nw = nw
wa._last_search[0] = -10.0

app = FastAPI()
app.router.routes.extend(wa.routes())
c = TestClient(app)

GEO = {"results": [{"name": "Wien", "latitude": 48.2, "longitude": 16.37, "country_code": "AT", "admin1": "Wien",
                    "country": "Österreich", "timezone": "Europe/Vienna"}]}
CRINITZ = {"results": [{"name": "Crinitz", "latitude": 51.7333, "longitude": 13.7667, "country_code": "DE",
                        "admin1": "Brandenburg", "country": "Deutschland", "timezone": "Europe/Berlin"}]}
CUR = {"weather": {"source_id": 1, "temperature": 3.0, "relative_humidity": 80, "icon": "cloudy"},
       "sources": [{"id": 1, "station_name": "Doberlug-Kirchhain", "distance": 12400}]}


def fake(routes: dict):
    calls: list[str] = []

    def f(url, headers):
        calls.append(url)
        for k, v in routes.items():
            if k in url:
                return json.loads(json.dumps(v))
        raise nw.urllib.error.URLError("no route")
    nw.fetch = f
    return calls


def frisch():
    for p in (nw.SETTINGS_FILE, nw.SECRETS_FILE):
        p.unlink(missing_ok=True)
    wa._last_search[0] = -10.0


class Ort(unittest.TestCase):
    def setUp(self):
        frisch()

    def test_ohne_ort(self):
        d = c.get("/api/weather").json()
        self.assertIsNone(d["place"])
        self.assertEqual({x["id"] for x in d["credits"]}, {"dwd", "brightsky", "openmeteo", "geonames"})
        self.assertIn("Quelle: Deutscher Wetterdienst", [x["notice"] for x in d["credits"]])

    def test_postleitzahl_freundlicher_hinweis_ohne_abfrage(self):
        calls = fake({"geocoding-api": {"results": [{"name": "New York City", "latitude": 40.7, "longitude": -74.0}]}})
        r = c.post("/api/weather/search", json={"query": "10115"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"], "Please enter the name of the place, for example Berlin.")
        self.assertEqual(calls, [])

    def test_suche_ortsname_und_speichern(self):
        calls = fake({"geocoding-api": CRINITZ, "/current_weather": CUR})
        r = c.post("/api/weather/search", json={"query": "Crinitz"})
        self.assertEqual(r.status_code, 200)
        hit = r.json()["results"][0]
        self.assertEqual((hit["name"], hit["country_code"]), ("Crinitz", "DE"))
        self.assertNotIn("postcode", hit)
        self.assertIn("geocoding-api.open-meteo.com", calls[0])
        d = c.post("/api/weather/place", json={"place": hit}).json()
        self.assertEqual(d["place"]["name"], "Crinitz")
        self.assertEqual(d["effective"], "dwd")
        self.assertEqual(stat.S_IMODE(nw.SETTINGS_FILE.stat().st_mode), 0o600)
        st = c.get("/api/weather/station").json()
        self.assertEqual((st["station"], st["distance_km"]), ("Doberlug-Kirchhain", 12.4))

    def test_ausland_waehlt_open_meteo(self):
        fake({"geocoding-api": GEO})
        hit = c.post("/api/weather/search", json={"query": "Wien"}).json()["results"][0]
        self.assertEqual(c.post("/api/weather/place", json={"place": hit}).json()["effective"], "openmeteo")

    def test_ungueltige_eingaben(self):
        self.assertEqual(c.post("/api/weather/search", json={"query": "x"}).status_code, 400)
        self.assertEqual(c.post("/api/weather/place", json={"place": {"lat": 99, "lon": 0}}).status_code, 400)
        self.assertEqual(c.post("/api/weather/place", json={"place": {"name": "X"}}).status_code, 400)
        self.assertEqual(c.post("/api/weather/place", content=b"[1]").status_code, 400)
        d = c.post("/api/weather/place", json={"place": {"name": "X" * 300, "lat": 1, "lon": 2, "timezone": "Mars/Base",
                                                         "country_code": "<b>"}}).json()
        self.assertEqual((len(d["place"]["name"]), d["place"]["timezone"], d["place"]["country_code"]), (80, "UTC", ""))

    def test_dienst_nicht_erreichbar(self):
        fake({})
        r = c.post("/api/weather/search", json={"query": "Wien"})
        self.assertEqual(r.status_code, 502)


class Optionen(unittest.TestCase):
    def setUp(self):
        frisch()
        c.post("/api/weather/place", json={"place": {"name": "Berlin", "lat": 52.52, "lon": 13.41, "country_code": "DE"}})

    def test_anbieter_und_eigene_instanz(self):
        d = c.post("/api/weather/options", json={"provider": "openmeteo", "brightsky_url": "https://bs.example.org/"}).json()
        self.assertEqual((d["provider"], d["effective"], d["brightsky_url"]), ("openmeteo", "openmeteo", "https://bs.example.org"))
        self.assertEqual(c.post("/api/weather/options", json={"provider": "x"}).status_code, 400)
        for bad in ("ftp://x", "https://u:p@x", "https://x/?a=1", "javascript:alert(1)"):
            self.assertEqual(c.post("/api/weather/options", json={"brightsky_url": bad}).status_code, 400, bad)
        d = c.post("/api/weather/options", json={"brightsky_url": ""}).json()
        self.assertEqual(d["brightsky_url"], "")

    def test_schluessel_nur_maskiert_und_loeschbar(self):
        d = c.post("/api/weather/keys", json={"openmeteo": "om-geheimer-schluessel-1234"}).json()
        self.assertNotIn("geheimer", json.dumps(d))
        self.assertTrue(d["keys"]["openmeteo"].endswith("1234"))
        self.assertEqual(set(d["keys"]), {"openmeteo"})
        self.assertEqual(stat.S_IMODE(nw.SECRETS_FILE.stat().st_mode), 0o600)
        self.assertEqual(c.post("/api/weather/keys", json={"openmeteo": "bad key with spaces"}).status_code, 400)
        self.assertEqual(c.post("/api/weather/keys", json={"openmeteo": ""}).json()["keys"]["openmeteo"], "")

    def test_test_knopf_und_loeschen(self):
        fake({"/current_weather": CUR, "/alerts": {"alerts": []}})
        d = c.post("/api/weather/test", json={"zeitraum": "jetzt", "lang": "de"}).json()
        self.assertFalse(d["error"])
        self.assertTrue(d["text"].startswith("Laut Deutschem Wetterdienst, Station Doberlug-Kirchhain"))
        c.post("/api/weather/keys", json={"openmeteo": "om-schluessel-12345"})
        d = c.post("/api/weather/clear", json={}).json()
        self.assertIsNone(d["place"])
        self.assertFalse(nw.SECRETS_FILE.exists())


if __name__ == "__main__":
    unittest.main()
