#!/usr/bin/env python3
"""NuOrb: Wetter (nur Standardbibliothek). Kern für das MCP-Werkzeug und die Verwaltung.

Quellen (alle Abfragen laufen vom NuOrb-Server des Nutzers aus, keine zentrale Stelle):
  * Deutschland: Deutscher Wetterdienst über Bright Sky (api.brightsky.dev, ohne Schlüssel). Messwerte der
    nächstgelegenen DWD-Station, MOSMIX-Vorhersage, amtliche Warnungen. Daten: DWD, CC BY 4.0.
  * Außerhalb Deutschlands: Open-Meteo (frei nur nicht-kommerziell; optional eigener Schlüssel). CC BY 4.0.
  * Optional WeatherXM Pro mit eigenem Schlüssel des Nutzers: nur die Messwerte, Vorhersage/Warnungen weiter vom DWD.
  * Ortssuche einmalig bei der Einrichtung: Ortsname über Open-Meteo Geocoding (GeoNames), Postleitzahl über
    OpenStreetMap Nominatim.

Gespeichert wird nur lokal: CONF/weather.json (Ort, Koordinaten, Anbieter), Schlüssel in CONF/weather.env (600).
Abfragen tragen nur gerundete Koordinaten (2 Nachkommastellen, etwa 1 km) und einen neutralen User-Agent.
Zwischenspeicher: Stationen 24 h, Messwerte 10 min, Warnungen 10 min, Vorhersage 60 min.

Sätze: DE/EN, Zahlen ausgeschrieben, ohne Gedankenstriche und Semikolons, fehlende Werte fallen weg.
Amtliche Warnungen werden unverändert wiedergegeben (Überschrift und Gültigkeit), siehe DWD-Bedingungen.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

# ------------------------------------------------------------------ Pfade und Einstellungen
DATA = Path(os.environ.get("HERMES_HOME", "/opt/data"))
CONF = Path(os.environ.get("NUORB_CONF", DATA / "nuorb" / "config"))
SETTINGS_FILE = CONF / "weather.json"
SECRETS_FILE = CONF / "weather.env"
CACHE_DIR = Path(os.environ.get("NUORB_WEATHER_CACHE", DATA / "nuorb" / "cache" / "weather"))

BRIGHTSKY_URL = "https://api.brightsky.dev"
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_PAID_URL = "https://customer-api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
WXM_URL = "https://pro.weatherxm.com/api/v1"
# Für Tests und e2e: alle Adressen auf einen lokalen Mock umbiegen (nie in der CI ins Internet)
_MOCK = os.environ.get("NUORB_WEATHER_MOCK", "").rstrip("/")
if _MOCK:
    BRIGHTSKY_URL, OPENMETEO_URL, OPENMETEO_PAID_URL = f"{_MOCK}/brightsky", f"{_MOCK}/openmeteo", f"{_MOCK}/openmeteo"
    GEOCODE_URL, NOMINATIM_URL, WXM_URL = f"{_MOCK}/geocode", f"{_MOCK}/nominatim", f"{_MOCK}/wxm"

USER_AGENT = "NuOrb weather (+https://github.com/anarki-lnx/nuorb)"
TTL = {"station": 24 * 3600, "current": 600, "alerts": 600, "forecast": 3600}
TIMEOUT = 10
PERIODS = ("jetzt", "heute", "morgen", "woche", "warnungen")
PROVIDERS = ("auto", "dwd", "openmeteo")


class WeatherError(Exception):
    """Fehler mit vorlesbarem Text (DE/EN)."""

    def __init__(self, de: str, en: str):
        super().__init__(en)
        self.de, self.en = de, en

    def text(self, lang: str) -> str:
        return self.de if lang == "de" else self.en


def _read_json(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_private(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".neu")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)


def load_settings() -> dict:
    s = _read_json(SETTINGS_FILE, {})
    return s if isinstance(s, dict) else {}


def save_settings(s: dict) -> None:
    _write_private(SETTINGS_FILE, json.dumps(s, ensure_ascii=False, indent=2) + "\n")


def load_secrets() -> dict:
    out: dict[str, str] = {}
    try:
        for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def save_secret(name: str, value: str | None) -> None:
    """Schlüssel setzen (leer/None = löschen). Wert nie loggen."""
    cur = load_secrets()
    if value:
        cur[name] = value.strip()
    else:
        cur.pop(name, None)
    _write_private(SECRETS_FILE, "".join(f"{k}={v}\n" for k, v in sorted(cur.items())))


# ------------------------------------------------------------------ HTTP und Zwischenspeicher
def _http_get(url: str, headers: dict[str, str]) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 (feste https-Adressen oder Mock)
        return json.loads(r.read().decode("utf-8"))


fetch: Callable[[str, dict[str, str]], Any] = _http_get   # in Tests ersetzbar


def _get(base: str, params: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        return fetch(f"{base}?{q}" if q else base, headers or {})
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise WeatherError("Der Wetterdienst lehnt den Schlüssel ab.", "The weather service rejected the key.")
        if e.code == 429:
            raise WeatherError("Der Wetterdienst meldet zu viele Abfragen. Bitte später noch einmal.",
                               "The weather service reports too many requests. Please try again later.")
        raise WeatherError("Der Wetterdienst ist gerade nicht erreichbar.", "The weather service is not reachable right now.")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise WeatherError("Der Wetterdienst ist gerade nicht erreichbar.", "The weather service is not reachable right now.")


def cached(kind: str, key: str, loader: Callable[[], Any]) -> Any:
    """Antwort aus dem Zwischenspeicher (TTL je Art) oder neu laden. Bei Fehler: abgelaufenen Wert nehmen, falls vorhanden."""
    p = CACHE_DIR / f"{kind}-{key}.json"
    alt = _read_json(p, None)
    if isinstance(alt, dict) and time.time() - alt.get("t", 0) < TTL[kind]:
        return alt["v"]
    try:
        v = loader()
    except WeatherError:
        if isinstance(alt, dict) and time.time() - alt.get("t", 0) < 6 * TTL[kind]:
            return alt["v"]
        raise
    try:
        _write_private(p, json.dumps({"t": time.time(), "v": v}, ensure_ascii=False))
    except OSError:
        pass
    return v


def _r(x: float) -> float:
    return round(float(x), 2)


def _key(lat: float, lon: float, extra: str = "") -> str:
    return f"{_r(lat):.2f}_{_r(lon):.2f}{('_' + extra) if extra else ''}".replace("-", "m")


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


# ------------------------------------------------------------------ Ortssuche (nur bei der Einrichtung)
def geocode(query: str, lang: str = "de", country: str = "DE") -> list[dict]:
    """Postleitzahl (nur Ziffern) über Nominatim, sonst Ortsname über Open-Meteo. Liefert bis zu 5 Treffer."""
    q = (query or "").strip()
    if not q:
        return []
    if q.replace(" ", "").isdigit():
        d = _get(NOMINATIM_URL, {"postalcode": q.replace(" ", ""), "country": country or "DE", "format": "jsonv2",
                                 "addressdetails": 1, "limit": 5, "accept-language": lang})
        out = []
        for e in d if isinstance(d, list) else []:
            a = e.get("address") or {}
            name = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or e.get("name") or q
            out.append({"name": name, "region": a.get("state") or "", "postcode": a.get("postcode") or q,
                        "country_code": str(a.get("country_code") or country).upper(),
                        "lat": float(e["lat"]), "lon": float(e["lon"]), "source": "nominatim",
                        "timezone": "Europe/Berlin" if str(a.get("country_code") or country).upper() == "DE" else "UTC"})
        return out
    d = _get(GEOCODE_URL, {"name": q, "count": 5, "language": lang, "format": "json"})
    return [{"name": e.get("name") or q, "region": ", ".join(x for x in (e.get("admin1"), e.get("country")) if x),
             "postcode": (e.get("postcodes") or [""])[0], "country_code": str(e.get("country_code") or "").upper(),
             "lat": float(e["latitude"]), "lon": float(e["longitude"]), "source": "open-meteo",
             "timezone": e.get("timezone") or "UTC"}
            for e in (d.get("results") or []) if "latitude" in e]


def provider_for(s: dict) -> str:
    p = s.get("provider") or "auto"
    if p == "auto":
        return "dwd" if str(s.get("country_code") or "").upper() == "DE" else "openmeteo"
    return p if p in PROVIDERS else "dwd"


# ------------------------------------------------------------------ Anbieter: einheitliche Werte
# current: temp, feels, humidity, wind_kmh, gust_kmh, wind_dir, precip_1h, pressure, sky, ts (ISO), station, distance_km
# day:     date (YYYY-MM-DD), tmin, tmax, precip, prob, sky
# alert:   headline, onset, expires, severity, event


def _sky_from_icon(icon: str | None, condition: str | None = None) -> str | None:
    c = (condition or "").lower()
    if c in ("rain", "sleet", "snow", "hail", "thunderstorm", "fog"):
        return c
    i = (icon or "").lower()
    for k in ("thunderstorm", "hail", "snow", "sleet", "rain", "fog", "wind", "cloudy", "partly-cloudy", "clear"):
        if i.startswith(k) or i == k:
            return "partly" if k == "partly-cloudy" else k
    return None


WMO_SKY = {0: "clear", 1: "clear", 2: "partly", 3: "cloudy", 45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle",
           55: "drizzle", 56: "sleet", 57: "sleet", 61: "rain", 63: "rain", 65: "heavyrain", 66: "sleet", 67: "sleet",
           71: "snow", 73: "snow", 75: "snow", 77: "snow", 80: "showers", 81: "showers", 82: "heavyrain", 85: "snow",
           86: "snow", 95: "thunderstorm", 96: "hail", 99: "hail"}


def _wmo(code: Any) -> str | None:
    return WMO_SKY.get(code) if isinstance(code, int) else None


def brightsky_current(lat: float, lon: float, base: str = BRIGHTSKY_URL) -> dict:
    def load():
        return _get(f"{base}/current_weather", {"lat": _r(lat), "lon": _r(lon)})
    d = cached("current", _key(lat, lon, "dwd"), load)
    w = d.get("weather") or {}
    src = {s.get("id"): s for s in d.get("sources") or []}.get(w.get("source_id")) or {}
    if w.get("temperature") is None and not src:
        raise WeatherError("Der Deutsche Wetterdienst liefert für diesen Ort gerade keine Messwerte.",
                           "The German Weather Service has no measurements for this place right now.")
    return {"temp": w.get("temperature"), "feels": None, "humidity": w.get("relative_humidity"),
            "wind_kmh": w.get("wind_speed_10") if w.get("wind_speed_10") is not None else w.get("wind_speed_30"),
            "gust_kmh": w.get("wind_gust_speed_10") if w.get("wind_gust_speed_10") is not None else w.get("wind_gust_speed_30"),
            "wind_dir": w.get("wind_direction_10"), "precip_1h": w.get("precipitation_60"), "pressure": w.get("pressure_msl"),
            "sky": _sky_from_icon(w.get("icon"), w.get("condition")), "ts": w.get("timestamp"),
            "station": _station_name(src.get("station_name")), "distance_km": (src.get("distance") or 0) / 1000 if src else None,
            "source": "dwd"}


def _station_name(n: str | None) -> str | None:
    if not n:
        return None
    return n.title() if n.isupper() else n


def brightsky_days(lat: float, lon: float, tz: str, days: int = 8, base: str = BRIGHTSKY_URL) -> list[dict]:
    heute = dt.datetime.now(ZoneInfo(tz)).date()
    last = heute + dt.timedelta(days=days)

    def load():
        return _get(f"{base}/weather", {"lat": _r(lat), "lon": _r(lon), "date": heute.isoformat(),
                                        "last_date": last.isoformat(), "tz": tz})
    d = cached("forecast", _key(lat, lon, f"dwd_{heute.isoformat()}"), load)
    tage: dict[str, list[dict]] = {}
    jetzt = dt.datetime.now(dt.timezone.utc)
    for h in d.get("weather") or []:
        try:
            t = dt.datetime.fromisoformat(h["timestamp"])
        except (KeyError, ValueError):
            continue
        datum = t.astimezone(ZoneInfo(tz)).date().isoformat()
        h = dict(h, _future=t >= jetzt - dt.timedelta(hours=1))
        tage.setdefault(datum, []).append(h)
    return [_aggregate(datum, hs) for datum, hs in sorted(tage.items())]


def _aggregate(datum: str, hs: list[dict]) -> dict:
    def vals(k):
        return [h[k] for h in hs if isinstance(h.get(k), (int, float))]
    temps, precip = vals("temperature"), vals("precipitation")
    probs = [h["precipitation_probability"] for h in hs if isinstance(h.get("precipitation_probability"), (int, float))]
    skies = [_sky_from_icon(h.get("icon"), h.get("condition")) for h in hs if 7 <= _hour(h) <= 20] or \
            [_sky_from_icon(h.get("icon"), h.get("condition")) for h in hs]
    rest = [h for h in hs if h.get("_future")]
    return {"date": datum, "tmin": min(temps) if temps else None, "tmax": max(temps) if temps else None,
            "precip": round(sum(precip), 1) if precip else None, "prob": max(probs) if probs else None,
            "sky": _dominant([s for s in skies if s]),
            "rest_tmax": max((h["temperature"] for h in rest if isinstance(h.get("temperature"), (int, float))), default=None),
            "rest_tmin": min((h["temperature"] for h in rest if isinstance(h.get("temperature"), (int, float))), default=None)}


def _hour(h: dict) -> int:
    try:
        return int(str(h.get("timestamp", ""))[11:13])
    except ValueError:
        return 12


RANG = ["thunderstorm", "hail", "heavyrain", "snow", "sleet", "rain", "showers", "drizzle", "fog", "wind", "cloudy",
        "partly", "clear"]


def _dominant(skies: list[str]) -> str | None:
    """Niederschlag schlägt Bewölkung, wenn er mindestens zwei Stunden vorkommt, sonst die häufigste Angabe."""
    if not skies:
        return None
    for s in RANG[:8]:
        if skies.count(s) >= 2:
            return s
    return max(set(skies), key=lambda s: (skies.count(s), -RANG.index(s) if s in RANG else 0))


def brightsky_alerts(lat: float, lon: float, base: str = BRIGHTSKY_URL) -> list[dict]:
    def load():
        return _get(f"{base}/alerts", {"lat": _r(lat), "lon": _r(lon)})
    d = cached("alerts", _key(lat, lon, "dwd"), load)
    out = []
    jetzt = dt.datetime.now(dt.timezone.utc)
    for a in d.get("alerts") or []:
        if a.get("status") not in (None, "actual"):
            continue
        try:
            if a.get("expires") and dt.datetime.fromisoformat(a["expires"]) < jetzt:
                continue
        except ValueError:
            pass
        out.append({"headline_de": a.get("headline_de"), "headline_en": a.get("headline_en"), "onset": a.get("onset"),
                    "expires": a.get("expires"), "severity": a.get("severity"), "event": a.get("event_en")})
    return out


def openmeteo_all(lat: float, lon: float, key: str | None = None) -> dict:
    base = OPENMETEO_PAID_URL if key else OPENMETEO_URL

    def load():
        return _get(base, {"latitude": _r(lat), "longitude": _r(lon), "timezone": "auto", "forecast_days": 8,
                           "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,"
                                      "wind_speed_10m,wind_gusts_10m,wind_direction_10m,pressure_msl",
                           "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                                    "precipitation_sum", "apikey": key or None})
    return cached("current", _key(lat, lon, "om"), load)


def openmeteo_current(lat: float, lon: float, key: str | None = None) -> dict:
    c = openmeteo_all(lat, lon, key).get("current") or {}
    return {"temp": c.get("temperature_2m"), "feels": c.get("apparent_temperature"), "humidity": c.get("relative_humidity_2m"),
            "wind_kmh": c.get("wind_speed_10m"), "gust_kmh": c.get("wind_gusts_10m"), "wind_dir": c.get("wind_direction_10m"),
            "precip_1h": c.get("precipitation"), "pressure": c.get("pressure_msl"), "sky": _wmo(c.get("weather_code")),
            "ts": None, "station": None, "distance_km": None, "source": "openmeteo"}


def openmeteo_days(lat: float, lon: float, key: str | None = None) -> list[dict]:
    d = openmeteo_all(lat, lon, key).get("daily") or {}
    out = []
    for i, datum in enumerate(d.get("time") or []):
        def v(k, i=i):
            arr = d.get(k) or []
            return arr[i] if i < len(arr) else None
        out.append({"date": datum, "tmin": v("temperature_2m_min"), "tmax": v("temperature_2m_max"),
                    "precip": v("precipitation_sum"), "prob": v("precipitation_probability_max"),
                    "sky": _wmo(v("weather_code")), "rest_tmax": None, "rest_tmin": None})
    return out


def wxm_near(lat: float, lon: float, key: str, radius_m: int = 10000) -> list[dict]:
    def load():
        return _get(f"{WXM_URL}/stations/near", {"lat": _r(lat), "lon": _r(lon), "radius": radius_m}, {"X-API-KEY": key})
    d = cached("station", _key(lat, lon, f"wxm{radius_m}"), load)
    liste = d if isinstance(d, list) else (d.get("stations") or d.get("data") or []) if isinstance(d, dict) else []
    out = []
    for s in liste:
        loc = s.get("location") or {}
        if loc.get("lat") is None or loc.get("lon") is None or not s.get("id"):
            continue
        out.append({"id": s["id"], "name": s.get("name") or s["id"],
                    "distance_km": round(distance_km(lat, lon, loc["lat"], loc["lon"]), 1)})
    return sorted(out, key=lambda s: s["distance_km"])


def wxm_current(station: dict, key: str) -> dict:
    def load():
        return _get(f"{WXM_URL}/stations/{urllib.parse.quote(station['id'], safe='')}/latest", {}, {"X-API-KEY": key})
    d = cached("current", "wxm_" + "".join(c for c in station["id"] if c.isalnum())[:40], load)
    o = d.get("observation") or {}
    if o.get("temperature") is None:
        raise WeatherError("Die WeatherXM-Station liefert gerade keine Messwerte.", "The WeatherXM station has no measurements right now.")

    def kmh(v):
        return v * 3.6 if isinstance(v, (int, float)) else None
    return {"temp": o.get("temperature"), "feels": o.get("feels_like"), "humidity": o.get("humidity"),
            "wind_kmh": kmh(o.get("wind_speed")), "gust_kmh": kmh(o.get("wind_gust")), "wind_dir": o.get("wind_direction"),
            "precip_1h": o.get("precipitation_rate"), "pressure": o.get("pressure"), "sky": _sky_from_icon(o.get("icon")),
            "ts": o.get("timestamp"), "station": station.get("name"), "distance_km": station.get("distance_km"), "source": "wxm"}


# ------------------------------------------------------------------ Zahlen in Worten
_DE = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf",
       "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn"]
_DE_Z = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig", "neunzig"]
_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
       "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_Z = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _de_int(n: int) -> str:
    if n < 20:
        return _DE[n]
    if n < 100:
        e, z = n % 10, n // 10
        return _DE_Z[z] if e == 0 else ("ein" if e == 1 else _DE[e]) + "und" + _DE_Z[z]
    if n < 1000:
        h, r = divmod(n, 100)
        return ("ein" if h == 1 else _DE[h]) + "hundert" + (_de_int(r) if r else "")
    t, r = divmod(n, 1000)
    return ("ein" if t == 1 else _de_int(t)) + "tausend" + (_de_int(r) if r else "")


def _en_int(n: int) -> str:
    if n < 20:
        return _EN[n]
    if n < 100:
        e, z = n % 10, n // 10
        return _EN_Z[z] + ("" if e == 0 else " " + _EN[e])
    if n < 1000:
        h, r = divmod(n, 100)
        return _EN[h] + " hundred" + (" " + _en_int(r) if r else "")
    t, r = divmod(n, 1000)
    return _en_int(t) + " thousand" + (" " + _en_int(r) if r else "")


def number(x: float, lang: str = "de", digits: int = 0, ein: bool = False) -> str:
    """0.8 -> 'null Komma acht' / 'zero point eight'. ein=True: 1 -> 'ein' (vor Einheiten im Deutschen)."""
    x = round(float(x), digits)
    neg, x = x < 0, abs(x)
    ganz = int(x)
    rest = round(x - ganz, digits)
    s = _de_int(ganz) if lang == "de" else _en_int(ganz)
    if rest > 0:
        ziffern = f"{rest:.{digits}f}".split(".")[1].rstrip("0")
        woerter = _DE if lang == "de" else _EN
        s += (" Komma " if lang == "de" else " point ") + " ".join(woerter[int(c)] for c in ziffern)
    elif lang == "de" and ein and ganz == 1:
        s = "ein"
    if neg and ganz + rest > 0:
        s = ("minus " if lang == "de" else "minus ") + s
    return s


def degrees(x: float, lang: str) -> str:
    n = number(x, lang, 1, ein=True)
    if lang == "de":
        return n + " Grad"
    return n + (" degree" if n == "one" else " degrees")


DIR_DE = ["Nord", "Nordost", "Ost", "Südost", "Süd", "Südwest", "West", "Nordwest"]
DIR_EN = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
SKY = {"clear": ("klar", "clear"), "partly": ("teils bewölkt", "partly cloudy"), "cloudy": ("bedeckt", "overcast"),
       "fog": ("neblig", "foggy"), "wind": ("windig", "windy"), "drizzle": ("Nieselregen", "drizzle"),
       "rain": ("Regen", "rain"), "showers": ("Regenschauer", "showers"), "heavyrain": ("starker Regen", "heavy rain"),
       "sleet": ("Schneeregen", "sleet"), "snow": ("Schnee", "snow"), "hail": ("Hagel", "hail"),
       "thunderstorm": ("Gewitter", "thunderstorms")}
WEEKDAY = (["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
           ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])


def _sky(s: str | None, lang: str) -> str | None:
    return SKY[s][0 if lang == "de" else 1] if s in SKY else None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _clock(iso: str | None, tz: str, lang: str) -> str:
    """'heute zwölf Uhr' / 'today at twelve'."""
    if not iso:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso).astimezone(ZoneInfo(tz))
    except ValueError:
        return ""
    tage = (t.date() - dt.datetime.now(ZoneInfo(tz)).date()).days
    if lang == "de":
        tag = {0: "heute", 1: "morgen", -1: "gestern"}.get(tage, WEEKDAY[0][t.weekday()])
        return f"{tag} {number(t.hour, 'de', ein=True)} Uhr" + (f" {number(t.minute, 'de')}" if t.minute else "")
    tag = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(tage, WEEKDAY[1][t.weekday()])
    h12 = t.hour % 12 or 12
    zeit = number(h12, "en") + (f" {number(t.minute, 'en')}" if t.minute else "") + (" a.m." if t.hour < 12 else " p.m.")
    if t.hour == 12 and not t.minute:
        zeit = "noon"
    elif t.hour == 0 and not t.minute:
        zeit = "midnight"
    return f"{tag} at {zeit}"


def _source_intro(cur: dict, place: str, lang: str) -> str:
    st, km = cur.get("station"), _num(cur.get("distance_km"))
    entf = ""
    if km is not None and km < 0.75:
        entf = " ganz in der Nähe" if lang == "de" else " nearby"
    elif km is not None:
        k = max(1, round(km))
        entf = (" in einem Kilometer Entfernung" if lang == "de" and k == 1 else
                f" in {number(k, 'de')} Kilometern Entfernung" if lang == "de" else
                f" {number(k, 'en')} kilometre{'s' if k != 1 else ''} away")
    if cur["source"] == "dwd":
        return (f"Laut Deutschem Wetterdienst, Station {st}{entf}" if lang == "de" and st else
                "Laut Deutschem Wetterdienst" if lang == "de" else
                f"According to the German Weather Service, station {st}{entf}" if st else
                "According to the German Weather Service")
    if cur["source"] == "wxm":
        return (f"Deine WeatherXM-Station {st}{entf} meldet" if lang == "de" else f"Your WeatherXM station {st}{entf} reports")
    return f"Laut Open-Meteo für {place}" if lang == "de" else f"According to Open-Meteo for {place}"


def sentence_now(cur: dict, place: str, lang: str, tz: str) -> str:
    teile = []
    t = _num(cur.get("temp"))
    if t is not None:
        s = degrees(t, lang)
        f = _num(cur.get("feels"))
        if f is not None and abs(f - t) >= 2:
            s += f", gefühlt {degrees(f, lang)}" if lang == "de" else f", feels like {degrees(f, lang)}"
        teile.append(s)
    sky = _sky(cur.get("sky"), lang)
    if sky:
        teile.append(sky)
    h = _num(cur.get("humidity"))
    if h is not None:
        teile.append(f"{number(round(h), lang)} Prozent Luftfeuchte" if lang == "de" else f"{number(round(h), lang)} percent humidity")
    w, g, r = _num(cur.get("wind_kmh")), _num(cur.get("gust_kmh")), _num(cur.get("wind_dir"))
    if w is not None:
        kmh = round(w)
        if kmh < 2 and (g is None or g < 10):
            teile.append("fast windstill" if lang == "de" else "almost calm")
        else:
            richtung = (DIR_DE if lang == "de" else DIR_EN)[int((r % 360) / 45 + 0.5) % 8] if r is not None else None
            if lang == "de":
                s = "Wind" + (f" aus {richtung}" if richtung else "") + f" mit {number(kmh, 'de', ein=True)} Kilometern pro Stunde"
                if g is not None and round(g) >= kmh + 5:
                    s += f", Böen bis {number(round(g), 'de')}"
            else:
                s = f"wind {number(kmh, 'en')} kilometres per hour" + (f" from the {richtung}" if richtung else "")
                if g is not None and round(g) >= kmh + 5:
                    s += f", gusts up to {number(round(g), 'en')}"
            teile.append(s)
    intro = _source_intro(cur, place, lang)
    if not teile:
        return intro + (": gerade keine Messwerte." if lang == "de" else ": no measurements right now.")
    trenner = " " if cur["source"] == "wxm" else ": "
    satz = intro + trenner + ", ".join(teile) + "."
    p = _num(cur.get("precip_1h"))
    if p is not None:
        if p >= 0.1:
            satz += (f" In der letzten Stunde fielen {number(p, 'de', 1)} Liter pro Quadratmeter." if lang == "de"
                     else f" {number(p, 'en', 1)} millimetres of rain in the last hour.")
        elif cur["source"] == "dwd":
            satz += " Kein Niederschlag in der letzten Stunde." if lang == "de" else " No precipitation in the last hour."
    if cur.get("ts"):
        try:
            alter = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(cur["ts"])).total_seconds() / 60
        except ValueError:
            alter = 0
        if alter > 90:
            satz += (f" Die Messung ist von {_clock(cur['ts'], tz, 'de')}." if lang == "de"
                     else f" The measurement is from {_clock(cur['ts'], tz, 'en')}.")
    return satz


def sentence_day(day: dict, name: str, src: str, lang: str, rest_only: bool = False) -> str:
    quelle = {"dwd": ("laut Deutschem Wetterdienst", "according to the German Weather Service"),
              "openmeteo": ("laut Open-Meteo", "according to Open-Meteo")}.get(src, ("", ""))[0 if lang == "de" else 1]
    teile = []
    sky = _sky(day.get("sky"), lang)
    if sky:
        teile.append(sky)
    lo, hi = (day.get("rest_tmin"), day.get("rest_tmax")) if rest_only and day.get("rest_tmax") is not None \
        else (day.get("tmin"), day.get("tmax"))
    lo, hi = _num(lo), _num(hi)
    if lo is not None and hi is not None:
        teile.append(f"zwischen {number(lo, 'de', 1)} und {degrees(hi, 'de')}" if lang == "de"
                     else f"between {number(lo, 'en', 1)} and {degrees(hi, 'en')}")
    prob = _num(day.get("prob"))
    if prob is not None:
        teile.append(f"Regenwahrscheinlichkeit bis {number(round(prob), 'de')} Prozent" if lang == "de"
                     else f"chance of rain up to {number(round(prob), 'en')} percent")
    pr = _num(day.get("precip"))
    if pr is not None and pr >= 0.5:
        teile.append(f"etwa {number(pr, 'de', 1)} Liter Niederschlag pro Quadratmeter" if lang == "de"
                     else f"about {number(pr, 'en', 1)} millimetres of precipitation")
    if not teile:
        return (f"Für {name} habe ich keine Vorhersage." if lang == "de" else f"I have no forecast for {name}.")
    return f"{name} {quelle}: " + ", ".join(teile) + "."


def sentence_week(days: list[dict], src: str, lang: str, tz: str) -> str:
    heute = dt.datetime.now(ZoneInfo(tz)).date()
    teile: list[str] = []
    for d in days:
        try:
            datum = dt.date.fromisoformat(d["date"])
        except (KeyError, ValueError):
            continue
        if datum <= heute or len(teile) >= 7 or _num(d.get("tmax")) is None:
            continue
        name = WEEKDAY[0 if lang == "de" else 1][datum.weekday()]
        sky = _sky(d.get("sky"), lang)
        hi = degrees(_num(d.get("tmax")) or 0, lang)
        teile.append(f"{name} {sky + ', ' if sky else ''}{'bis' if lang == 'de' else 'up to'} {hi}.")
    if not teile:
        return "Eine Vorhersage für die nächsten Tage habe ich gerade nicht." if lang == "de" else \
            "I have no forecast for the next days right now."
    kopf = {"dwd": ("Die nächsten Tage laut Deutschem Wetterdienst.", "The next days according to the German Weather Service."),
            "openmeteo": ("Die nächsten Tage laut Open-Meteo.", "The next days according to Open-Meteo.")}[src][0 if lang == "de" else 1]
    return kopf + " " + " ".join(teile)


def sentence_alerts(alerts: list[dict] | None, lang: str, tz: str, brief: bool = False) -> str:
    """Amtliche Warnungen unverändert: Überschrift wie vom DWD, dazu die Gültigkeit."""
    if alerts is None:
        return "" if brief else ("Amtliche Warnungen kann ich nur für Orte in Deutschland abrufen." if lang == "de"
                                 else "Official warnings are only available for places in Germany.")
    if not alerts:
        return "" if brief else ("Der Deutsche Wetterdienst meldet keine amtlichen Warnungen für deinen Ort." if lang == "de"
                                 else "The German Weather Service reports no official warnings for your place.")
    teile = []
    for a in alerts[:4]:
        kopf = (a.get("headline_de") if lang == "de" else a.get("headline_en")) or a.get("headline_de") or a.get("headline_en")
        if not kopf:
            continue
        zeit = ""
        if a.get("onset") and a.get("expires") and not brief:
            zeit = (f", gültig von {_clock(a['onset'], tz, 'de')} bis {_clock(a['expires'], tz, 'de')}" if lang == "de"
                    else f", valid from {_clock(a['onset'], tz, 'en')} until {_clock(a['expires'], tz, 'en')}")
        elif a.get("expires"):
            zeit = f" bis {_clock(a['expires'], tz, 'de')}" if lang == "de" else f" until {_clock(a['expires'], tz, 'en')}"
        teile.append(kopf + zeit + ".")
    if brief:
        return (" Der Deutsche Wetterdienst warnt: " if lang == "de" else " The German Weather Service warns: ") + " ".join(teile)
    return ("Der Deutsche Wetterdienst meldet: " if lang == "de" else "The German Weather Service reports: ") + " ".join(teile)


# ------------------------------------------------------------------ Bericht
def report(period: str = "jetzt", lang: str = "de", settings: dict | None = None) -> tuple[str, bool]:
    """Fertiger, vorlesbarer Text und ob es ein Fehler ist."""
    s = settings if settings is not None else load_settings()
    lang = "en" if lang == "en" else "de"
    period = period if period in PERIODS else "jetzt"
    if s.get("lat") is None or s.get("lon") is None:
        return ("Das Wetter ist noch nicht eingerichtet. Bitte in der Verwaltung unter Wetter den Ort eintragen." if lang == "de"
                else "Weather is not set up yet. Please enter your place in the admin panel under Weather."), True
    lat, lon = float(s["lat"]), float(s["lon"])
    place, tz = s.get("name") or ("deinen Ort" if lang == "de" else "your place"), s.get("timezone") or "Europe/Berlin"
    prov = provider_for(s)
    sec = load_secrets()
    om_key = sec.get("OPENMETEO_API_KEY") or None
    base = s.get("brightsky_url") or BRIGHTSKY_URL
    try:
        if period == "warnungen":
            return sentence_alerts(brightsky_alerts(lat, lon, base) if prov == "dwd" else None, lang, tz), False
        if period == "woche":
            days = brightsky_days(lat, lon, tz, base=base) if prov == "dwd" else openmeteo_days(lat, lon, om_key)
            return sentence_week(days, prov, lang, tz), False
        if period in ("heute", "morgen"):
            days = brightsky_days(lat, lon, tz, base=base) if prov == "dwd" else openmeteo_days(lat, lon, om_key)
            ziel = dt.datetime.now(ZoneInfo(tz)).date() + dt.timedelta(days=0 if period == "heute" else 1)
            tag = next((d for d in days if d.get("date") == ziel.isoformat()), None)
            name = {"heute": ("Heute", "Today"), "morgen": ("Morgen", "Tomorrow")}[period][0 if lang == "de" else 1]
            text = sentence_day(tag, name, prov, lang, rest_only=period == "heute") if tag else \
                (f"Für {name.lower()} habe ich keine Vorhersage." if lang == "de" else f"I have no forecast for {name.lower()}.")
            if prov == "dwd":
                text += sentence_alerts(_overlapping(_alerts_soft(lat, lon, base), ziel, tz), lang, tz, brief=True)
            return text, False
        # jetzt
        cur = None
        wxm = s.get("wxm_station") if s.get("measure") == "wxm" else None
        if wxm and sec.get("WXM_API_KEY"):
            try:
                cur = wxm_current(wxm, sec["WXM_API_KEY"])
            except WeatherError:
                cur = None   # Rückfall auf DWD/Open-Meteo
        if cur is None:
            cur = brightsky_current(lat, lon, base) if prov == "dwd" else openmeteo_current(lat, lon, om_key)
        text = sentence_now(cur, place, lang, tz)
        if prov == "dwd":
            text += sentence_alerts(_alerts_soft(lat, lon, base), lang, tz, brief=True)
        return text, False
    except WeatherError as e:
        return e.text(lang), True


def _overlapping(alerts: list[dict], day: dt.date, tz: str) -> list[dict]:
    """Nur Warnungen, die den gefragten Tag berühren (ohne Ende: gelten weiter)."""
    start = dt.datetime.combine(day, dt.time.min, ZoneInfo(tz))
    out = []
    for a in alerts:
        try:
            ende = dt.datetime.fromisoformat(a["expires"]) if a.get("expires") else None
            beginn = dt.datetime.fromisoformat(a["onset"]) if a.get("onset") else None
        except ValueError:
            ende = beginn = None
        if (ende is None or ende > start) and (beginn is None or beginn < start + dt.timedelta(days=1)):
            out.append(a)
    return out


def _alerts_soft(lat: float, lon: float, base: str) -> list[dict]:
    try:
        return brightsky_alerts(lat, lon, base)
    except WeatherError:
        return []


def station_info(s: dict | None = None) -> dict:
    """Für die Verwaltung: Anbieter, nächste Station und Entfernung (nutzt den Zwischenspeicher)."""
    s = s if s is not None else load_settings()
    if s.get("lat") is None:
        return {"configured": False}
    prov = provider_for(s)
    out: dict[str, Any] = {"configured": True, "provider": prov, "name": s.get("name"), "region": s.get("region")}
    try:
        if prov == "dwd":
            cur = brightsky_current(float(s["lat"]), float(s["lon"]), s.get("brightsky_url") or BRIGHTSKY_URL)
            out.update(station=cur.get("station"), distance_km=round(cur.get("distance_km") or 0, 1))
        sec = load_secrets()
        if s.get("measure") == "wxm" and s.get("wxm_station"):
            out["wxm_station"] = s["wxm_station"]
            out["wxm_key_set"] = bool(sec.get("WXM_API_KEY"))
    except WeatherError as e:
        out["error"] = e.en
    return out
