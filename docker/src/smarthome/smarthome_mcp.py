#!/usr/bin/env python3
"""NuOrb-Smarthome: MCP-Server (stdio, nur Python-Standardbibliothek) fuer Home Assistant und ioBroker.

Ein Skript, zwei Hermes-Eintraege (Hermes prueft Bestaetigungen pro Server, wie bei "zuhause"):
  smarthome_mcp.py lesen    --zugang <datei>  -> Server "smarthome"          (trust: full, alles readOnly)
       geraete, zustand, raeume
  smarthome_mcp.py schalten --zugang <datei>  -> Server "smarthome_schalten" (trust: untrusted -> Bestaetigungskarte)
       schalten (Licht, Steckdose, Schalter: an/aus/umschalten, Helligkeit), szene

Zugang (Datei, chmod 600, wird nie ausgegeben; Zeilen KEY=WERT, nicht benoetigte weglassen):
  HA_URL=http://homeassistant.local:8123      HA_TOKEN=<Long-Lived Access Token>
  IOB_URL=http://iobroker.local:8093          IOB_TOKEN=<OAuth2-Token>  oder  IOB_USER=… IOB_PASS=…
  IOB_API=rest-api|simple-api                 (Standard: rest-api)
Nur gesetzte Systeme werden benutzt. Keine Adressen oder Geraete sind im Code hinterlegt.

Welche Geraete NuOrb sieht:
  Home Assistant: Entitaeten der Domains light, switch, input_boolean, scene, sensor, binary_sensor
                  (Raum = HA-Bereich). Optional HA_NUR_ASSIST=1: nur fuer Assist freigegebene Entitaeten.
  ioBroker:       Datenpunkte, die einer Funktion (enum.functions.*) ODER einem Raum (enum.rooms.*) zugeordnet
                  sind – dieselbe Auswahl, die ioBroker auch fuer Sprachassistenten nutzt.
Direkt ohne Modell (Test):  python3 smarthome_mcp.py --satz <werkzeug> '<json>' --zugang <datei>
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENDE = " Rufe das Werkzeug ohne vorherigen Text auf und sprich erst nach dem Ergebnis."
SPRICH = " Das Ergebnis ist ein fertiger Satz: fast woertlich sprechen, nichts erfinden."
ARTEN = ["licht", "steckdose", "schalter", "szene", "sensor", "alle"]
ART_WOERTER = {"licht": ("licht", "lichter", "lampe", "lampen", "leuchte", "beleuchtung"),
               "steckdose": ("steckdose", "steckdosen", "zwischenstecker"),
               "schalter": ("schalter",), "szene": ("szene", "szenen", "stimmung"),
               "sensor": ("sensor", "sensoren", "temperatur", "feuchte", "luftfeuchtigkeit", "fenster", "tuer")}
ZUGANG = {}
SYSTEME = {"home_assistant": "Home Assistant", "iobroker": "ioBroker"}


# ---------- Hilfen ----------
EINER = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf",
         "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn"]
ZEHNER = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig", "neunzig"]


def anzahl(n, einzahl, mehrzahl, weiblich=False):
    """'ein Gerät', 'eine Szene', 'zwei Geräte'."""
    if n == 1:
        return ("eine " if weiblich else "ein ") + einzahl
    return zahlwort(n) + " " + mehrzahl


def zahlwort(n: int) -> str:
    n = int(round(n))
    if n < 0:
        return "minus " + zahlwort(-n)
    if n < 20:
        return EINER[n]
    if n < 100:
        e, z = n % 10, n // 10
        return ZEHNER[z] if e == 0 else ("ein" if e == 1 else EINER[e]) + "und" + ZEHNER[z]
    if n < 1000:
        h, r = divmod(n, 100)
        return ("ein" if h == 1 else EINER[h]) + "hundert" + (zahlwort(r) if r else "")
    return str(n)


def zahl(x) -> str:
    """Sprechbare Zahl, eine Nachkommastelle."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if abs(f - round(f)) < 0.05:
        return zahlwort(round(f))
    ganz, rest = divmod(round(abs(f) * 10), 10)
    return ("minus " if f < 0 else "") + zahlwort(ganz) + " Komma " + EINER[rest]


EINHEIT = {"°C": "Grad", "%": "Prozent", "W": "Watt", "kW": "Kilowatt", "kWh": "Kilowattstunden", "lx": "Lux",
           "hPa": "Hektopascal", "V": "Volt", "A": "Ampere"}


def norm(s) -> str:
    s = str(s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def name_text(n) -> str:
    """ioBroker-Namen koennen {de:…, en:…} sein."""
    if isinstance(n, dict):
        return n.get("de") or n.get("en") or next(iter(n.values()), "")
    return str(n or "")


def http(methode, url, daten=None, kopf=None, timeout=8):
    h = {"Accept": "application/json"}
    h.update(kopf or {})
    body = None
    if daten is not None:
        body = json.dumps(daten).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=methode)
    with urllib.request.urlopen(req, timeout=timeout) as a:
        roh = a.read()
    try:
        return json.loads(roh or b"null")
    except json.JSONDecodeError:
        return roh.decode("utf-8", "replace")


# ---------- Home Assistant ----------
class HomeAssistant:
    system = "home_assistant"

    def __init__(self, url, token):
        self.url, self.kopf = url.rstrip("/"), {"Authorization": f"Bearer {token}"}

    def _bereiche(self):
        vorlage = ("{% for s in states %}{% set a = area_name(s.entity_id) %}{% if a %}"
                   "{{ s.entity_id }}\t{{ a }}\n{% endif %}{% endfor %}")
        r = http("POST", self.url + "/api/template", {"template": vorlage}, self.kopf)
        return dict(z.split("\t", 1) for z in str(r).splitlines() if "\t" in z)

    def geraete(self):
        zustaende = http("GET", self.url + "/api/states", kopf=self.kopf)
        raum = self._bereiche()
        erlaubt = None
        if ZUGANG.get("HA_NUR_ASSIST") == "1":
            erlaubt = self._assist_freigegeben()
        aus = []
        for s in zustaende:
            eid, attr, st = s["entity_id"], s.get("attributes", {}), s.get("state")
            dom = eid.split(".")[0]
            if erlaubt is not None and eid not in erlaubt:
                continue
            if dom == "light":
                art = "licht"
            elif dom in ("switch", "input_boolean"):
                art = "steckdose" if attr.get("device_class") == "outlet" else "schalter"
            elif dom == "scene":
                art = "szene"
            elif dom in ("sensor", "binary_sensor"):
                art = "sensor"
            else:
                continue
            g = {"id": eid, "system": self.system, "name": attr.get("friendly_name") or eid, "raum": raum.get(eid, ""),
                 "art": art, "erreichbar": st != "unavailable" and (art == "szene" or st != "unknown")}
            if art in ("licht", "steckdose", "schalter"):
                g["an"] = st == "on"
                if art == "licht" and st == "on" and attr.get("brightness") is not None:
                    g["helligkeit"] = round(attr["brightness"] / 255 * 100)
            elif dom == "binary_sensor":
                g["an"] = st == "on"
                g["klasse"] = attr.get("device_class") or ""
            elif art == "sensor":
                g["wert"], g["einheit"] = st, attr.get("unit_of_measurement") or ""
            aus.append(g)
        return aus

    def _assist_freigegeben(self):
        # Nicht ueber REST verfuegbar; die Freigabe steht im Entitaetsregister (WebSocket). Ohne WebSocket-Bibliothek:
        # Vorlage mit is_state_attr geht nicht; daher: Hinweis und keine Filterung.
        return None

    def schalten(self, g, an, helligkeit=None):
        dom = g["id"].split(".")[0]
        if g["art"] == "szene":
            dienst, daten = "scene/turn_on", {"entity_id": g["id"]}
        else:
            dienst = f"{dom}/" + ("turn_on" if an else "turn_off")
            daten = {"entity_id": g["id"]}
            if an and helligkeit is not None and dom == "light":
                daten["brightness_pct"] = max(1, min(100, int(helligkeit)))
        http("POST", f"{self.url}/api/services/{dienst}", daten, self.kopf)

    def neu_lesen(self, g):
        s = http("GET", f"{self.url}/api/states/{g['id']}", kopf=self.kopf)
        attr = s.get("attributes", {})
        r = {"an": s.get("state") == "on"}
        if attr.get("brightness") is not None and s.get("state") == "on":
            r["helligkeit"] = round(attr["brightness"] / 255 * 100)
        return r


# ---------- ioBroker ----------
class IoBroker:
    """ioBroker ueber den Adapter rest-api (Standard, /v1/…) oder simple-api."""
    system = "iobroker"

    def __init__(self, url, api="rest-api", token=None, user=None, passwort=None):
        self.url, self.api = url.rstrip("/"), api
        self.kopf, self.query = {}, {}
        if token:
            self.kopf["Authorization"] = f"Bearer {token}"
        elif user:
            self.kopf["Authorization"] = "Basic " + base64.b64encode(f"{user}:{passwort or ''}".encode()).decode()

    def _get(self, pfad, **q):
        q = {k: v for k, v in q.items() if v is not None}
        return http("GET", self.url + pfad + ("?" + urllib.parse.urlencode(q) if q else ""), kopf=self.kopf)

    def _objekte(self, muster, typ=None):
        if self.api == "simple-api":
            return self._get("/objects", pattern=muster, type=typ)
        r = self._get("/v1/objects", filter=muster, type=typ)
        return r if isinstance(r, dict) else {}

    def _zustaende(self, ids):
        if not ids:
            return {}
        if self.api == "simple-api":
            r = self._get("/getBulk/" + ",".join(urllib.parse.quote(i, safe="") for i in ids))
            return {e["id"]: e.get("val") for e in r if isinstance(e, dict)}
        aus = {}
        for i in ids:  # rest-api: einzeln (klein genug fuer Haushalte; getBulk gibt es dort nicht ueberall)
            try:
                s = self._get("/v1/state/" + urllib.parse.quote(i, safe=""))
                aus[i] = s.get("val") if isinstance(s, dict) else None
            except urllib.error.HTTPError:
                aus[i] = None
        return aus

    def geraete(self):
        raeume = self._objekte("enum.rooms.*", "enum")
        funktionen = self._objekte("enum.functions.*", "enum")
        raum_von, funk_von = {}, {}
        for eid, o in raeume.items():
            for m in (o.get("common") or {}).get("members") or []:
                raum_von[m] = name_text((o.get("common") or {}).get("name")) or eid.split(".")[-1]
        for eid, o in funktionen.items():
            for m in (o.get("common") or {}).get("members") or []:
                funk_von[m] = eid.split(".")[-1].lower()
        mitglieder = set(raum_von) | set(funk_von)
        # Mitglieder koennen Kanaele/Geraete sein -> ihre Datenpunkte einsammeln
        punkte = {}
        for m in mitglieder:
            for pid, o in self._objekte(m + "*").items():
                if o.get("type") == "state" and (pid == m or pid.startswith(m + ".")):
                    oberes = m if pid != m else pid
                    punkte[pid] = (o, oberes)
        werte = self._zustaende(list(punkte))
        aus = []
        for pid, (o, oberes) in punkte.items():
            c = o.get("common") or {}
            rolle = str(c.get("role") or "")
            funk = funk_von.get(oberes, funk_von.get(pid, ""))
            schreibbar = c.get("write", True) and c.get("type") == "boolean"
            if rolle.startswith("scene") or funk in ("scenes", "szenen", "scene"):
                art = "szene"
            elif schreibbar and (rolle in ("switch.light",) or funk in ("light", "licht", "beleuchtung", "lighting")):
                art = "licht"
            elif schreibbar and (funk in ("socket", "steckdose", "steckdosen", "plug") or "socket" in rolle):
                art = "steckdose"
            elif schreibbar and rolle.startswith("switch"):
                art = "schalter"
            elif rolle.startswith(("value", "sensor", "indicator")) or not c.get("write", True):
                art = "sensor"
            else:
                continue
            name = name_text(c.get("name")) or pid.split(".")[-1]
            if oberes != pid:  # Datenpunkt eines Kanals: Kanalname benutzen
                try:
                    kanal = self._objekte(oberes).get(oberes) or {}
                    name = name_text((kanal.get("common") or {}).get("name")) or name
                except Exception:
                    pass
            g = {"id": pid, "system": self.system, "name": name, "raum": raum_von.get(oberes, raum_von.get(pid, "")),
                 "art": art, "erreichbar": werte.get(pid) is not None}
            w = werte.get(pid)
            if art in ("licht", "steckdose", "schalter") or (art == "sensor" and c.get("type") == "boolean"):
                g["an"] = w is True or str(w).lower() == "true"
                g["klasse"] = next((k for r, k in (("window", "window"), ("door", "door"), ("motion", "motion"))
                                    if r in rolle), "")
            elif art == "sensor":
                g["wert"], g["einheit"] = w, c.get("unit") or ""
            aus.append(g)
        return aus

    def schalten(self, g, an, helligkeit=None):
        wert = True if g["art"] == "szene" else bool(an)
        i = urllib.parse.quote(g["id"], safe="")
        if self.api == "simple-api":
            self._get(f"/set/{i}", value=str(wert).lower())
        else:
            http("PATCH", f"{self.url}/v1/state/{i}", {"val": wert}, self.kopf)

    def neu_lesen(self, g):
        w = self._zustaende([g["id"]]).get(g["id"])
        return {"an": w is True or str(w).lower() == "true"}


def backends():
    b = []
    if ZUGANG.get("HA_URL") and ZUGANG.get("HA_TOKEN"):
        b.append(HomeAssistant(ZUGANG["HA_URL"], ZUGANG["HA_TOKEN"]))
    if ZUGANG.get("IOB_URL"):
        b.append(IoBroker(ZUGANG["IOB_URL"], ZUGANG.get("IOB_API", "rest-api"), ZUGANG.get("IOB_TOKEN"),
                          ZUGANG.get("IOB_USER"), ZUGANG.get("IOB_PASS")))
    return b


def alle_geraete(system=None):
    gs, fehler = [], []
    for b in backends():
        if system and system != "alle" and b.system != system:
            continue
        try:
            gs += b.geraete()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            code = getattr(exc, "code", None)
            fehler.append(f"{SYSTEME[b.system]} ist nicht erreichbar" + (" (Zugang abgelehnt)" if code in (401, 403) else ""))
    return gs, fehler


# ---------- Namenssuche ----------
def passt_art(g, art):
    return not art or art == "alle" or g["art"] == art


def finde(gs, name, raum=None, art=None):
    """Beste Treffer fuer einen gesprochenen Namen. Versteht auch 'Kuechenlicht' = Raum Kueche + Licht."""
    q = norm(name)
    if raum:
        gs = [g for g in gs if norm(raum) in norm(g["raum"]) or norm(g["raum"]) in norm(raum)] or gs
    ohne_art = gs
    gs = [g for g in gs if passt_art(g, art)]
    if not q:
        return gs
    if art and art != "alle":  # Modelle raten die Art oft falsch (Kaffeemaschine als "schalter"): dann ohne Art-Filter
        treffer = finde(gs, name)
        return treffer if treffer else finde(ohne_art, name)
    woerter = q.split()
    # Art-Woerter im Namen ("licht", "lampe" …) als Filter merken
    art_aus_name = next((a for a, ws in ART_WOERTER.items() if any(w in ws or any(w.endswith(x) for x in ws if len(x) > 4)
                                                                    for w in woerter)), None)
    beste, punkte = [], 0
    for g in gs:
        n, r = norm(g["name"]), norm(g["raum"])
        voll = f"{n} {r}"
        if q == n:
            p = 100
        elif q in n or (len(n) > 3 and n in q):
            p = 80
        elif all(w in voll or any(w.startswith(t[:5]) for t in voll.split() if len(t) >= 5) for w in woerter
                 if w not in sum(ART_WOERTER.values(), ())):
            p = 60 if (art_aus_name is None or g["art"] == art_aus_name) else 0
        elif r and any(w.startswith(r[:4]) for w in woerter) and art_aus_name and g["art"] == art_aus_name:
            p = 55  # Kompositum: "kuechenlicht" -> Raum Kueche, Art Licht
        else:
            p = 0
        if p > punkte:
            beste, punkte = [g], p
        elif p == punkte and p > 0:
            beste.append(g)
    return beste


def bezeichnung(g):
    return g["name"] + (f" ({g['raum']})" if g["raum"] and norm(g["raum"]) not in norm(g["name"]) else "")


def zustand_satz(g):
    n = bezeichnung(g)
    if not g.get("erreichbar", True):
        return f"{n} ist gerade nicht erreichbar."
    if g["art"] == "szene":
        return f"{n} ist eine Szene."
    if "an" in g and g["art"] != "sensor":
        s = f"{n} ist {'an' if g['an'] else 'aus'}"
        if g.get("helligkeit") is not None:
            s += f", Helligkeit {zahlwort(g['helligkeit'])} Prozent"
        return s + "."
    if "an" in g:  # binaerer Sensor
        k = g.get("klasse", "")
        if k in ("window", "door", "opening", "garage_door"):
            return f"{n} ist {'offen' if g['an'] else 'geschlossen'}."
        if k in ("motion", "occupancy", "presence"):
            return f"{n} meldet {'Bewegung' if g['an'] else 'keine Bewegung'}."
        return f"{n} meldet {'an' if g['an'] else 'aus'}."
    e = g.get("einheit") or ""
    return f"{n} meldet {zahl(g.get('wert'))} {EINHEIT.get(e, e)}".rstrip() + "."


def aufzaehlen(teile):
    return teile[0] if len(teile) == 1 else ", ".join(teile[:-1]) + " und " + teile[-1]


# ---------- Werkzeuge ----------
def geraete(a):
    gs, fehler = alle_geraete(a.get("system"))
    art = a.get("art") or "alle"
    gs = [g for g in gs if passt_art(g, art)]
    if a.get("raum"):
        gs = [g for g in gs if norm(a["raum"]) in norm(g["raum"]) or (g["raum"] and norm(g["raum"]) in norm(a["raum"]))]
    nur_an = bool(a.get("nur_an"))
    if nur_an:
        gs = [g for g in gs if g.get("an") and g["art"] != "sensor"]
    wort = {"licht": "Lichter", "steckdose": "Steckdosen", "schalter": "Schalter", "szene": "Szenen",
            "sensor": "Sensoren", "alle": "Geräte"}[art]
    ort = f" im Bereich {a['raum']}" if a.get("raum") else ""
    if not gs:
        satz = (f"Es sind keine {wort}{ort} eingeschaltet." if nur_an else f"Ich finde keine {wort}{ort}.")
    elif nur_an:
        einzahl = {"licht": "Licht", "steckdose": "Steckdose", "schalter": "Schalter", "szene": "Szene",
                   "sensor": "Sensor", "alle": "Gerät"}[art]
        satz = (f"Eingeschaltet {'ist' if len(gs) == 1 else 'sind'}{ort} "
                f"{anzahl(len(gs), einzahl, wort, weiblich=art in ('steckdose', 'szene'))}: "
                + aufzaehlen([bezeichnung(g) for g in gs]) + ".")
    elif art in ("sensor",) or len(gs) <= 8:
        satz = " ".join(zustand_satz(g) for g in gs)
    else:
        an = [g for g in gs if g.get("an")]
        satz = (f"Ich kenne {zahlwort(len(gs))} {wort}{ort}, davon {'ist' if len(an) == 1 else 'sind'} "
                f"{zahlwort(len(an))} an" + (": " + aufzaehlen([bezeichnung(g) for g in an]) if an else "") + ".")
    if fehler:
        satz += " Achtung: " + "; ".join(fehler) + "."
    roh = [{k: g.get(k) for k in ("id", "system", "name", "raum", "art", "an", "helligkeit", "wert", "einheit")} for g in gs[:40]]
    return satz + "\n\n" + json.dumps(roh, ensure_ascii=False), bool(fehler) and not gs


def zustand(a):
    gs, fehler = alle_geraete(a.get("system"))
    treffer = finde(gs, a.get("name", ""), a.get("raum"), a.get("art"))
    if not treffer:
        return ("Ich finde kein Gerät mit dem Namen " + str(a.get("name")) + "." + (" " + "; ".join(fehler) + "." if fehler else ""),
                bool(fehler))
    return " ".join(zustand_satz(g) for g in treffer[:6]), False


def raeume(a):
    gs, fehler = alle_geraete(a.get("system"))
    r = {}
    for g in gs:
        r.setdefault(g["raum"] or "ohne Raum", []).append(g)
    if not r:
        return "Ich finde keine Räume." + (" " + "; ".join(fehler) + "." if fehler else ""), bool(fehler)
    teile = []
    for name, liste in sorted(r.items()):
        an = [g for g in liste if g["art"] == "licht" and g.get("an")]
        teile.append(f"{name}: {anzahl(len(liste), 'Gerät', 'Geräte')}"
                     + (f", davon {anzahl(len(an), 'Licht', 'Lichter')} an" if an else ""))
    return "Räume: " + "; ".join(teile) + "." + (" Achtung: " + "; ".join(fehler) + "." if fehler else ""), False


def _backend(g):
    return next(b for b in backends() if b.system == g["system"])


def _schalte(liste, an, helligkeit):
    saetze = []
    for g in liste:
        _backend(g).schalten(g, an, helligkeit)
    time.sleep(0.6)
    for g in liste:
        if g["art"] == "szene":
            saetze.append(f"Die Szene {g['name']} ist aktiviert.")
            continue
        jetzt = {}
        for _ in range(6):
            jetzt = _backend(g).neu_lesen(g)
            if jetzt.get("an") == bool(an):
                break
            time.sleep(0.5)
        if jetzt.get("an") == bool(an):
            s = f"{bezeichnung(g)} ist jetzt {'an' if an else 'aus'}"
            if an and jetzt.get("helligkeit") is not None and helligkeit is not None:
                s += f", Helligkeit {zahlwort(jetzt['helligkeit'])} Prozent"
            saetze.append(s + ".")
        else:
            saetze.append(f"{bezeichnung(g)}: Befehl gesendet, aber das Gerät meldet noch {'an' if jetzt.get('an') else 'aus'}.")
    return " ".join(saetze)


def schalten(a):
    aktion = str(a.get("aktion") or "").strip().lower()
    # Modelle weichen gern vom enum ab ("ein", "on" …): tolerant annehmen statt eine zweite Bestaetigungskarte auszuloesen
    aktion = {"ein": "an", "einschalten": "an", "anschalten": "an", "on": "an", "true": "an", "1": "an",
              "ausschalten": "aus", "off": "aus", "false": "aus", "0": "aus",
              "um": "umschalten", "toggle": "umschalten", "wechseln": "umschalten"}.get(aktion, aktion)
    if aktion not in ("an", "aus", "umschalten"):
        return "aktion muss 'an', 'aus' oder 'umschalten' sein.", True
    gs, fehler = alle_geraete(a.get("system"))
    gs = [g for g in gs if g["art"] in ("licht", "steckdose", "schalter")]
    treffer = finde(gs, a.get("name", ""), a.get("raum"), a.get("art"))
    if not treffer:
        return f"Ich finde nichts Schaltbares mit dem Namen {a.get('name')}." + (" " + "; ".join(fehler) + "." if fehler else ""), True
    if len(treffer) > 1 and not a.get("alle"):
        return ("Das ist nicht eindeutig. Meinst du " + aufzaehlen([bezeichnung(g) for g in treffer[:6]]).replace(" und ", " oder ")
                + "? Es wurde nichts geschaltet."), True
    if aktion == "umschalten" and a.get("helligkeit"):
        an = True  # "auf zwanzig Prozent" ist immer ein Einschalten
    elif aktion == "umschalten":
        an = not treffer[0].get("an")
    else:
        an = aktion == "an"
    hell = a.get("helligkeit")
    return _schalte(treffer, an, hell), False


def szene(a):
    gs, fehler = alle_geraete(a.get("system"))
    treffer = finde([g for g in gs if g["art"] == "szene"], a.get("name", ""))
    if len(treffer) != 1:
        alle = [g["name"] for g in gs if g["art"] == "szene"]
        return (("Nicht eindeutig. " if treffer else "Diese Szene gibt es nicht. ")
                + ("Verfügbar: " + aufzaehlen(alle) + "." if alle else "Es sind keine Szenen eingerichtet.")), True
    return _schalte(treffer, True, None), False


# ---------- MCP-Beschreibung ----------
def _t(name, titel, text, props=None, req=None, ro=True):
    return {"name": name, "title": titel, "description": text + SPRICH + ENDE,
            "inputSchema": {"type": "object", "properties": props or {}, "required": req or [],
                            "additionalProperties": False},
            "annotations": {"readOnlyHint": ro, "destructiveHint": False, "openWorldHint": False}}


SYSTEM = {"type": "string", "enum": ["home_assistant", "iobroker", "alle"],
          "description": "Nur ein bestimmtes Smart-Home-System; leer = alle eingerichteten."}
RAUM = {"type": "string", "description": "Raum/Bereich, z. B. 'Küche', 'Wohnzimmer'; leer = alle."}
NAME = {"type": "string", "description": "Gerätename wie gesprochen, z. B. 'Küchenlicht', 'Stehlampe', 'Kaffeemaschine'."}
TOOLS_LESEN = [
    _t("geraete", "Smart Home: Geräte und Zustände",
       "Listet Lichter, Steckdosen, Schalter, Szenen und Sensoren aus Home Assistant/ioBroker mit Zustand. "
       "IMMER bei Fragen wie 'Welche Lichter sind an?', 'Was ist im Wohnzimmer an?', 'Welche Sensoren gibt es?'. "
       "art: licht|steckdose|schalter|szene|sensor|alle. nur_an: true fuer 'was ist an'.",
       {"art": {"type": "string", "enum": ARTEN}, "raum": RAUM, "nur_an": {"type": "boolean"}, "system": SYSTEM}),
    _t("zustand", "Smart Home: ein Gerät oder Sensor",
       "Zustand eines Geraets oder Messwert eines Sensors (Temperatur, Fenster, Bewegung, Helligkeit) aus "
       "Home Assistant/ioBroker. IMMER bei 'Ist das Küchenlicht an?', 'Wie warm ist es im Wohnzimmer?'.",
       {"name": NAME, "raum": RAUM, "art": {"type": "string", "enum": ARTEN}, "system": SYSTEM}, ["name"]),
    _t("raeume", "Smart Home: Räume",
       "Welche Raeume/Bereiche es gibt, wie viele Geraete darin sind und wo Licht an ist.", {"system": SYSTEM}),
]
TOOLS_SCHALTEN = [
    _t("schalten", "Smart Home: Gerät schalten",
       "Schaltet ein Licht, eine Steckdose oder einen Schalter in Home Assistant/ioBroker ein, aus oder um; "
       "bei Licht optional mit Helligkeit in Prozent. Der Nutzer bestaetigt vorher auf dem Bildschirm. "
       "Bei mehreren Treffern nur mit alle=true alle schalten (z. B. 'alle Lichter in der Küche aus').",
       {"name": NAME, "aktion": {"type": "string", "description": "'an', 'aus' oder 'umschalten'"},
        "helligkeit": {"type": "integer", "minimum": 1, "maximum": 100}, "raum": RAUM,
        "art": {"type": "string", "enum": ["licht", "steckdose", "schalter"]}, "alle": {"type": "boolean"},
        "system": SYSTEM}, ["name", "aktion"], ro=False),
    _t("szene", "Smart Home: Szene aktivieren",
       "Aktiviert eine Szene in Home Assistant/ioBroker (z. B. 'Filmabend', 'Gute Nacht'). "
       "Der Nutzer bestaetigt vorher auf dem Bildschirm.",
       {"name": {"type": "string", "description": "Name der Szene"}, "system": SYSTEM}, ["name"], ro=False),
]
FUNK = {f.__name__: f for f in (geraete, zustand, raeume, schalten, szene)}


# ---------- MCP ----------
def antwort(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    msg["error" if error is not None else "result"] = error if error is not None else result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def aufrufen(name, args):
    if not backends():
        return ("Es ist kein Smart-Home-System eingerichtet. In der NuOrb-Verwaltung Adresse und Token für "
                "Home Assistant oder ioBroker eintragen."), True
    try:
        return FUNK[name](args)
    except urllib.error.HTTPError as exc:
        return f"Das Smart-Home-System hat abgelehnt (HTTP {exc.code}). Es wurde nichts verändert.", True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"Das Smart-Home-System ist gerade nicht erreichbar ({exc.__class__.__name__}).", True
    except Exception as exc:  # noqa: BLE001
        return f"Interner Fehler: {exc}", True


def main(teil):
    tools = TOOLS_SCHALTEN if teil == "schalten" else TOOLS_LESEN
    namen = {t["name"] for t in tools}
    for zeile in sys.stdin:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            req = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        mid, methode, params = req.get("id"), req.get("method", ""), req.get("params") or {}
        if mid is None:
            continue
        if methode == "initialize":
            antwort(mid, {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": f"nuorb-smarthome-{teil}", "version": "1.0.0"}})
        elif methode == "ping":
            antwort(mid, {})
        elif methode == "tools/list":
            antwort(mid, {"tools": tools})
        elif methode == "tools/call":
            name = params.get("name", "")
            if name not in namen:
                antwort(mid, error={"code": -32602, "message": f"Unbekanntes Werkzeug: {name}"})
                continue
            text, fehler = aufrufen(name, params.get("arguments") or {})
            antwort(mid, {"content": [{"type": "text", "text": text}], "isError": fehler})
        else:
            antwort(mid, error={"code": -32601, "message": f"Methode nicht unterstuetzt: {methode}"})


def zugang_laden(pfad):
    if not pfad or not os.path.exists(pfad):
        return {}
    d = {}
    for z in open(pfad, encoding="utf-8"):
        z = z.strip()
        if z and not z.startswith("#") and "=" in z:
            k, v = z.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


if __name__ == "__main__":
    argv = sys.argv[1:]
    pfad = os.path.expanduser("~/.hermes/smarthome.env")
    if "--zugang" in argv:
        i = argv.index("--zugang")
        pfad = argv[i + 1]
        del argv[i:i + 2]
    ZUGANG.update(zugang_laden(pfad))
    if len(argv) >= 2 and argv[0] == "--satz":
        if argv[1] not in ("geraete", "zustand", "raeume"):  # Schalten nur ueber MCP mit Bestaetigungskarte
            sys.exit("--satz nur fuer lesende Werkzeuge: geraete, zustand, raeume")
        text, fehler = aufrufen(argv[1], json.loads(argv[2]) if len(argv) > 2 else {})
        print(text)
        sys.exit(1 if fehler else 0)
    main(argv[0] if argv else "lesen")
