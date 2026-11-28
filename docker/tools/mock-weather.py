#!/usr/bin/env python3
"""Mini-Mock für Wettertests: tut so, als wäre es Bright Sky (DWD), Open-Meteo, die Ortssuche und WeatherXM Pro.
Keine echten Abfragen. NuOrb nutzt ihn mit NUORB_WEATHER_MOCK=http://127.0.0.1:<port> (nur Tests/e2e).
Start: python3 docker/tools/mock-weather.py [port]   (Standard 18435, nur 127.0.0.1)
Jede Anfrage wird als eine Zeile JSON auf stdout protokolliert (Pfad, Query, User-Agent, ob ein Schlüssel kam).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18435
UTC = dt.timezone.utc


def now() -> dt.datetime:
    return dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


def brightsky(path: str) -> dict:
    t = now()
    if path.endswith("/current_weather"):
        return {"weather": {"source_id": 1, "timestamp": (t - dt.timedelta(minutes=20)).isoformat(), "temperature": 4.6,
                            "relative_humidity": 81, "wind_speed_10": 12.0, "wind_gust_speed_10": 30.0, "wind_direction_10": 225,
                            "precipitation_60": 0.4, "pressure_msl": 1012.0, "condition": "rain", "icon": "rain"},
                "sources": [{"id": 1, "station_name": "Teststation", "distance": 3200}]}
    if path.endswith("/weather"):
        start = t.replace(hour=0) - dt.timedelta(hours=1)
        hours = [{"timestamp": (start + dt.timedelta(hours=i)).isoformat(), "temperature": 2.0 + (i % 24) / 4,
                  "precipitation": 0.2, "precipitation_probability": 60, "condition": "rain", "icon": "rain"}
                 for i in range(24 * 9)]
        return {"weather": hours, "sources": []}
    if path.endswith("/alerts"):
        return {"alerts": [{"status": "actual", "onset": (t - dt.timedelta(hours=1)).isoformat(),
                            "expires": (t + dt.timedelta(hours=5)).isoformat(), "severity": "minor", "event_en": "wind gusts",
                            "headline_de": "Amtliche WARNUNG vor WINDBÖEN", "headline_en": "Official WARNING of WIND GUSTS"}],
                "location": {"name": "Teststadt"}}
    return {}


def openmeteo() -> dict:
    tage = [(dt.date.today() + dt.timedelta(days=i)).isoformat() for i in range(8)]
    return {"current": {"temperature_2m": 18.5, "apparent_temperature": 18.0, "relative_humidity_2m": 55, "precipitation": 0.0,
                        "weather_code": 1, "wind_speed_10m": 8.0, "wind_gusts_10m": 15.0, "wind_direction_10m": 90},
            "daily": {"time": tage, "weather_code": [1] * 8, "temperature_2m_max": [22.0] * 8, "temperature_2m_min": [12.0] * 8,
                      "precipitation_probability_max": [5] * 8, "precipitation_sum": [0.0] * 8}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # eigenes Protokoll
        pass

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        print(json.dumps({"path": u.path, "query": u.query, "ua": self.headers.get("User-Agent", ""),
                          "key": bool(self.headers.get("X-API-KEY"))}), flush=True)
        if not self.headers.get("User-Agent", "").startswith("NuOrb"):
            return self.send(400, {"error": "user agent"})
        p = u.path
        if p.startswith("/brightsky/"):
            return self.send(200, brightsky(p))
        if p.startswith("/openmeteo"):
            return self.send(200, openmeteo())
        if p.startswith("/geocode"):
            return self.send(200, {"results": [{"name": "Teststadt", "latitude": 52.0, "longitude": 13.0, "country_code": "DE",
                                                "admin1": "Testland", "country": "Deutschland", "timezone": "Europe/Berlin"}]})
        if p.startswith("/nominatim"):
            return self.send(200, [{"lat": "52.0", "lon": "13.0", "name": "Teststadt",
                                    "address": {"town": "Teststadt", "state": "Testland", "postcode": "12345", "country_code": "de"}}])
        if p.startswith("/wxm/"):
            if not self.headers.get("X-API-KEY"):
                return self.send(401, {"error": "key"})
            if p.endswith("/stations/near"):
                return self.send(200, [{"id": "wxm-test", "name": "Gartenstation", "location": {"lat": 52.001, "lon": 13.001}}])
            if p.endswith("/latest"):
                return self.send(200, {"observation": {"timestamp": now().isoformat(), "temperature": 5.5, "humidity": 77,
                                                       "wind_speed": 2.0, "wind_direction": 180, "icon": "cloudy"}})
        self.send(404, {"error": "not found"})

    def send(self, code: int, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
