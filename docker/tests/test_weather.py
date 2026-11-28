"""Unit-Tests für docker/app/nuorb_weather.py und nuorb_weather_mcp.py: alle Quellen gemockt, keine echten Abfragen."""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import shutil
import stat
import sys
import time
import unittest
import urllib.error
import urllib.parse

from _lade import APP, lade, temp_ordner

T = temp_ordner("weather")
ENV = {"HERMES_HOME": str(T), "NUORB_CONF": str(T / "conf"), "NUORB_WEATHER_CACHE": str(T / "cache"), "NUORB_LANG": "de"}
nw = lade("nuorb_weather", APP / "nuorb_weather.py", ENV)
mcp = lade("nuorb_weather_mcp_test", APP / "nuorb_weather_mcp.py", ENV)

UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
BERLIN = {"name": "Berlin", "lat": 52.5244, "lon": 13.4105, "country_code": "DE", "timezone": "Europe/Berlin"}
WIEN = {"name": "Wien", "lat": 48.21, "lon": 16.37, "country_code": "AT", "timezone": "Europe/Vienna"}


def iso(t: dt.datetime) -> str:
    return t.isoformat()


def bs_current(**w) -> dict:
    weather = {"source_id": 1, "timestamp": iso(NOW - dt.timedelta(minutes=20)), "temperature": 0.2, "relative_humidity": 67,
               "wind_speed_10": 14.0, "wind_gust_speed_10": 24.1, "wind_direction_10": 100, "precipitation_60": 0.0,
               "pressure_msl": 1037.8, "condition": "dry", "icon": "cloudy"}
    weather.update(w)
    return {"weather": weather, "sources": [{"id": 1, "station_name": "Berlin-Tempelhof", "distance": 5835}]}


def bs_hours() -> dict:
    hours = []
    start = dt.datetime.combine(dt.datetime.now(nw.ZoneInfo("Europe/Berlin")).date(), dt.time.min,
                                nw.ZoneInfo("Europe/Berlin")).astimezone(UTC)
    for i in range(24 * 8):
        t = start + dt.timedelta(hours=i)
        tag = i // 24
        hours.append({"timestamp": iso(t), "temperature": -2.0 + tag + (i % 24) / 6, "precipitation": 0.5 if tag == 1 else 0.0,
                      "precipitation_probability": 70 if tag == 1 else 10, "condition": "rain" if tag == 1 else "dry",
                      "icon": "rain" if tag == 1 else "partly-cloudy-day"})
    return {"weather": hours, "sources": []}


def bs_alerts(onset: dt.datetime, expires: dt.datetime) -> dict:
    return {"alerts": [{"status": "actual", "onset": iso(onset), "expires": iso(expires), "severity": "minor",
                        "event_en": "frost", "headline_de": "Amtliche WARNUNG vor FROST",
                        "headline_en": "Official WARNING of FROST"}]}


OM = {"current": {"temperature_2m": 0.4, "apparent_temperature": -3.7, "relative_humidity_2m": 76, "precipitation": 0.0,
                  "weather_code": 3, "wind_speed_10m": 10.5, "wind_gusts_10m": 27.0, "wind_direction_10m": 338,
                  "pressure_msl": 1030.0},
      "daily": {"time": [(dt.date.today() + dt.timedelta(days=i)).isoformat() for i in range(8)],
                "weather_code": [2, 61, 3, 3, 0, 0, 1, 2], "temperature_2m_max": [1.4, 3.0, 2, 2, 2, 2, 2, 2],
                "temperature_2m_min": [-3.9, -1.0, 0, 0, 0, 0, 0, 0], "precipitation_probability_max": [0, 80, 0, 0, 0, 0, 0, 0],
                "precipitation_sum": [0, 4.2, 0, 0, 0, 0, 0, 0]}}


class Fake:
    """Ersetzt nw.fetch: Antwort je URL-Teil, zählt Abrufe, merkt sich URLs und Kopfzeilen."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, headers: dict):
        self.calls.append((url, headers))
        for part, v in self.routes.items():
            if part in url:
                if isinstance(v, Exception):
                    raise v
                return json.loads(json.dumps(v))
        raise urllib.error.URLError("no route " + url)


def neu(routes: dict) -> Fake:
    shutil.rmtree(T / "cache", ignore_errors=True)
    shutil.rmtree(T / "conf", ignore_errors=True)
    f = Fake(routes)
    nw.fetch = f
    return f


DE_ROUTES = lambda: {"/current_weather": bs_current(), "/weather": bs_hours(),  # noqa: E731
                     "/alerts": bs_alerts(NOW - dt.timedelta(hours=1), NOW + dt.timedelta(hours=3))}


def sprechbar(test: unittest.TestCase, text: str) -> None:
    """Für Nutzer: keine Gedankenstriche, keine Semikolons, keine Ziffern (Zahlen ausgeschrieben)."""
    test.assertNotRegex(text, "[\u2013\u2014;]")
    test.assertNotRegex(text, r"\d", text)


class Zahlen(unittest.TestCase):
    def test_deutsch(self):
        self.assertEqual(nw.number(0.8, "de", 1), "null Komma acht")
        self.assertEqual(nw.number(-2.1, "de", 1), "minus zwei Komma eins")
        self.assertEqual(nw.number(21, "de"), "einundzwanzig")
        self.assertEqual(nw.number(1037, "de"), "eintausendsiebenunddreißig")
        self.assertEqual(nw.degrees(1.0, "de"), "ein Grad")
        self.assertEqual(nw.degrees(-0.04, "de"), "null Grad")

    def test_englisch(self):
        self.assertEqual(nw.number(0.2, "en", 1), "zero point two")
        self.assertEqual(nw.number(67, "en"), "sixty seven")
        self.assertEqual(nw.degrees(1, "en"), "one degree")
        self.assertEqual(nw.degrees(-3.7, "en"), "minus three point seven degrees")


class Deutschland(unittest.TestCase):
    def test_jetzt_mit_station_entfernung_und_warnung(self):
        neu(DE_ROUTES())
        text, err = nw.report("jetzt", "de", BERLIN)
        self.assertFalse(err)
        self.assertIn("Laut Deutschem Wetterdienst, Station Berlin-Tempelhof in sechs Kilometern Entfernung", text)
        self.assertIn("null Komma zwei Grad", text)
        self.assertIn("Böen bis vierundzwanzig", text)
        self.assertIn("Amtliche WARNUNG vor FROST", text)   # amtliche Warnung unverändert
        sprechbar(self, text)

    def test_englisch(self):
        neu(DE_ROUTES())
        text, _ = nw.report("jetzt", "en", BERLIN)
        self.assertIn("According to the German Weather Service, station Berlin-Tempelhof six kilometres away", text)
        self.assertIn("Official WARNING of FROST", text)
        sprechbar(self, text)

    def test_fehlende_werte_fallen_weg(self):
        neu({"/current_weather": bs_current(relative_humidity=None, wind_speed_10=None, wind_speed_30=None,
                                            icon=None, condition=None), "/alerts": {"alerts": []}})
        text, err = nw.report("jetzt", "de", BERLIN)
        self.assertFalse(err)
        self.assertNotIn("Luftfeuchte", text)
        self.assertNotIn("Wind", text)
        self.assertNotIn("warnt", text)

    def test_alte_messung_wird_genannt(self):
        neu({"/current_weather": bs_current(timestamp=iso(NOW - dt.timedelta(hours=3))), "/alerts": {"alerts": []}})
        self.assertIn("Die Messung ist von", nw.report("jetzt", "de", BERLIN)[0])

    def test_morgen_woche_heute(self):
        neu(DE_ROUTES())
        morgen, _ = nw.report("morgen", "de", BERLIN)
        self.assertIn("Morgen laut Deutschem Wetterdienst: Regen", morgen)
        self.assertIn("Regenwahrscheinlichkeit bis siebzig Prozent", morgen)
        self.assertIn("Liter Niederschlag pro Quadratmeter", morgen)
        self.assertNotIn("WARNUNG", morgen)   # Warnung endet heute, gilt also nicht für morgen
        woche, _ = nw.report("woche", "de", BERLIN)
        self.assertTrue(woche.startswith("Die nächsten Tage laut Deutschem Wetterdienst."))
        self.assertEqual(woche.count(" bis "), 7)
        heute, _ = nw.report("heute", "en", BERLIN)
        self.assertTrue(heute.startswith("Today according to the German Weather Service"))
        for t in (morgen, woche, heute):
            sprechbar(self, t)

    def test_warnungen(self):
        neu(DE_ROUTES())
        text, _ = nw.report("warnungen", "de", BERLIN)
        self.assertTrue(text.startswith("Der Deutsche Wetterdienst meldet: Amtliche WARNUNG vor FROST, gültig von"))
        sprechbar(self, text)
        neu({"/alerts": {"alerts": []}})
        self.assertIn("keine amtlichen Warnungen", nw.report("warnungen", "de", BERLIN)[0])

    def test_abgelaufene_warnung_wird_ignoriert(self):
        neu({"/alerts": bs_alerts(NOW - dt.timedelta(hours=5), NOW - dt.timedelta(hours=1))})
        self.assertIn("keine amtlichen Warnungen", nw.report("warnungen", "de", BERLIN)[0])

    def test_koordinaten_gerundet_und_neutraler_user_agent(self):
        f = neu(DE_ROUTES())
        nw.report("jetzt", "de", BERLIN)
        url = f.calls[0][0]
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(q["lat"], ["52.52"])
        self.assertEqual(q["lon"], ["13.41"])
        self.assertTrue(url.startswith("https://api.brightsky.dev/"))
        self.assertTrue(nw.USER_AGENT.startswith("NuOrb"))

    def test_eigene_bright_sky_instanz(self):
        f = neu(DE_ROUTES())
        nw.report("jetzt", "de", {**BERLIN, "brightsky_url": "http://brightsky.example:5000"})
        self.assertTrue(all(u.startswith("http://brightsky.example:5000/") for u, _ in f.calls))


class Ausland(unittest.TestCase):
    def test_open_meteo_automatisch(self):
        f = neu({"openmeteo": OM, "open-meteo.com": OM})
        text, err = nw.report("jetzt", "de", WIEN)
        self.assertFalse(err)
        self.assertTrue(text.startswith("Laut Open-Meteo für Wien: null Komma vier Grad, gefühlt minus drei Komma sieben Grad"))
        self.assertTrue(all("brightsky" not in u for u, _ in f.calls))
        sprechbar(self, text)
        morgen, _ = nw.report("morgen", "en", WIEN)
        self.assertIn("Tomorrow according to Open-Meteo: rain", morgen)

    def test_keine_warnungen_ausserhalb(self):
        neu({"open-meteo.com": OM})
        self.assertIn("nur für Orte in Deutschland", nw.report("warnungen", "de", WIEN)[0])

    def test_eigener_schluessel_nutzt_kundenadresse(self):
        f = neu({"open-meteo.com": OM})
        nw.save_secret("OPENMETEO_API_KEY", "om-test-123")
        nw.report("jetzt", "de", WIEN)
        self.assertTrue(f.calls[0][0].startswith("https://customer-api.open-meteo.com/"))


class WeatherXM(unittest.TestCase):
    SET = {**BERLIN, "measure": "wxm", "wxm_station": {"id": "st-1", "name": "Gartenstation", "distance_km": 0.4}}
    OBS = {"observation": {"timestamp": iso(NOW), "temperature": 3.5, "feels_like": 0.5, "humidity": 88, "wind_speed": 5.0,
                           "wind_gust": 9.0, "wind_direction": 270, "precipitation_rate": 0.0, "icon": "cloudy"}}

    def test_messwerte_von_wxm_schluessel_nie_im_text(self):
        f = neu({**DE_ROUTES(), "/stations/st-1/latest": self.OBS})
        nw.save_secret("WXM_API_KEY", "geheim-wxm-schluessel")
        text, err = nw.report("jetzt", "de", self.SET)
        self.assertFalse(err)
        self.assertTrue(text.startswith("Deine WeatherXM-Station Gartenstation ganz in der Nähe meldet "
                                        "drei Komma fünf Grad, gefühlt null Komma fünf Grad"))
        self.assertIn("Wind aus West mit achtzehn Kilometern pro Stunde", text)   # 5 m/s
        self.assertNotIn("geheim", text)
        self.assertEqual(f.calls[0][1].get("X-API-KEY"), "geheim-wxm-schluessel")
        self.assertNotIn("geheim", f.calls[0][0])   # Schlüssel nur im Kopf, nie in der URL

    def test_rueckfall_auf_dwd(self):
        neu({**DE_ROUTES(), "/stations/st-1/latest": urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO())})  # type: ignore[arg-type]
        nw.save_secret("WXM_API_KEY", "falsch")
        text, err = nw.report("jetzt", "de", self.SET)
        self.assertFalse(err)
        self.assertTrue(text.startswith("Laut Deutschem Wetterdienst"))

    def test_naechste_stationen(self):
        neu({"/stations/near": [{"id": "b", "name": "Weit", "location": {"lat": 52.60, "lon": 13.41}},
                                {"id": "a", "name": "Nah", "location": {"lat": 52.525, "lon": 13.411}}]})
        st = nw.wxm_near(52.5244, 13.4105, "k")
        self.assertEqual([s["id"] for s in st], ["a", "b"])
        self.assertLess(st[0]["distance_km"], 1)


class Zwischenspeicher(unittest.TestCase):
    def test_innerhalb_der_frist_kein_neuer_abruf(self):
        f = neu(DE_ROUTES())
        nw.report("jetzt", "de", BERLIN)
        n = len(f.calls)
        nw.report("jetzt", "de", BERLIN)
        self.assertEqual(len(f.calls), n)

    def test_abgelaufen_neu_laden_und_bei_fehler_alten_wert_nehmen(self):
        f = neu(DE_ROUTES())
        nw.report("jetzt", "de", BERLIN)
        for p in (T / "cache").glob("current-*.json"):
            d = json.loads(p.read_text())
            d["t"] = time.time() - nw.TTL["current"] - 5
            p.write_text(json.dumps(d))
        f.routes["/current_weather"] = urllib.error.URLError("weg")
        text, err = nw.report("jetzt", "de", BERLIN)
        self.assertFalse(err)
        self.assertIn("Berlin-Tempelhof", text)

    def test_fristen(self):
        self.assertEqual(nw.TTL["station"], 86400)
        self.assertLessEqual(nw.TTL["current"], 600)
        self.assertEqual(nw.TTL["alerts"], 600)


class Fehler(unittest.TestCase):
    def test_nicht_eingerichtet(self):
        neu({})
        text, err = nw.report("jetzt", "de", {})
        self.assertTrue(err)
        self.assertIn("noch nicht eingerichtet", text)

    def test_nicht_erreichbar(self):
        neu({})
        text, err = nw.report("jetzt", "en", BERLIN)
        self.assertTrue(err)
        self.assertEqual(text, "The weather service is not reachable right now.")

    def test_zu_viele_abfragen(self):
        neu({"/current_weather": urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO())})  # type: ignore[arg-type]
        self.assertIn("zu viele Abfragen", nw.report("jetzt", "de", BERLIN)[0])


class Ortssuche(unittest.TestCase):
    def test_postleitzahl_ueber_nominatim(self):
        f = neu({"nominatim": [{"lat": "51.73", "lon": "13.77", "name": "Crinitz",
                                "address": {"village": "Crinitz", "state": "Brandenburg", "postcode": "03246", "country_code": "de"}}]})
        r = nw.geocode("03246", "de")
        self.assertEqual(r[0]["name"], "Crinitz")
        self.assertEqual(r[0]["country_code"], "DE")
        self.assertEqual(r[0]["timezone"], "Europe/Berlin")
        self.assertIn("postalcode=03246", f.calls[0][0])

    def test_ortsname_ueber_open_meteo(self):
        f = neu({"geocoding-api": {"results": [{"name": "Wien", "latitude": 48.2, "longitude": 16.37, "country_code": "AT",
                                                "admin1": "Wien", "country": "Österreich", "timezone": "Europe/Vienna"}]}})
        r = nw.geocode("Wien", "de")
        self.assertEqual((r[0]["country_code"], r[0]["timezone"]), ("AT", "Europe/Vienna"))
        self.assertIn("geocoding-api.open-meteo.com", f.calls[0][0])
        self.assertEqual(nw.provider_for({"country_code": "AT"}), "openmeteo")
        self.assertEqual(nw.provider_for({"country_code": "DE"}), "dwd")


class Dateien(unittest.TestCase):
    def test_schluesseldatei_nur_fuer_den_besitzer(self):
        neu({})
        nw.save_secret("WXM_API_KEY", "abc")
        nw.save_settings({"name": "X"})
        for p in (nw.SECRETS_FILE, nw.SETTINGS_FILE):
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        nw.save_secret("WXM_API_KEY", "")
        self.assertNotIn("WXM_API_KEY", nw.load_secrets())


class Mcp(unittest.TestCase):
    def rpc(self, *reqs: dict) -> list[dict]:
        alt_in, alt_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO("".join(json.dumps(r) + "\n" for r in reqs)), io.StringIO()
        try:
            mcp.main()
            return [json.loads(z) for z in sys.stdout.getvalue().splitlines()]
        finally:
            sys.stdin, sys.stdout = alt_in, alt_out

    def test_werkzeug_nur_lesend(self):
        out = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tool = out[0]["result"]["tools"][0]
        self.assertEqual(tool["name"], "wetter")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertEqual(tool["inputSchema"]["properties"]["zeitraum"]["enum"], list(nw.PERIODS))

    def test_aufruf_in_der_sprache_des_assistenten(self):
        neu(DE_ROUTES())
        nw.save_settings(BERLIN)
        (T / "conf" / "ui.json").write_text(json.dumps({"lang": "en"}))
        out = self.rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "wetter", "arguments": {"zeitraum": "jetzt"}}})
        res = out[0]["result"]
        self.assertFalse(res["isError"])
        self.assertTrue(res["content"][0]["text"].startswith("According to the German Weather Service"))


class Texte(unittest.TestCase):
    def test_keine_striche_im_skill_und_in_meldungen(self):
        skill = (APP / "skills/wetter/SKILL.md").read_text(encoding="utf-8")
        self.assertNotRegex(skill, "[\u2013\u2014]")
        src = (APP / "nuorb_weather.py").read_text(encoding="utf-8")
        for m in re.finditer(r'WeatherError\("([^"]+)", "([^"]+)"\)', src):
            self.assertNotRegex(m.group(1) + m.group(2), "[\u2013\u2014;]")


if __name__ == "__main__":
    unittest.main()
