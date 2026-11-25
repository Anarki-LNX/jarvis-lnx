---
name: smarthome
description: "Fragen zu Licht, Steckdosen, Schaltern, Szenen und Sensoren im Smart Home (Home Assistant, ioBroker) IMMER mit den Werkzeugen mcp__smarthome__* beantworten bzw. mit mcp__smarthome_schalten__* schalten, nie raten. Schalten bestaetigt der Nutzer auf dem Bildschirm."
version: 1.0.0
metadata:
  hermes:
    tags: [smarthome, home-assistant, iobroker, licht, steckdose, szene, nuorb]
    category: smart-home
---

# Smart Home: Home Assistant und ioBroker

## When to Use
Jede Frage, welche Lichter/Steckdosen/Geraete an sind, nach einem Sensorwert (Temperatur, Fenster, Bewegung)
oder nach Raeumen, und jeder Wunsch, ein Licht, eine Steckdose oder einen Schalter zu schalten oder eine Szene
zu aktivieren.

## Procedure
1. Passendes Werkzeug ohne vorherigen Text aufrufen:
   - "Welche Lichter sind an?": `mcp__smarthome__geraete{art: "licht", nur_an: true}`
   - "Was ist im Wohnzimmer an?": `mcp__smarthome__geraete{raum: "Wohnzimmer", nur_an: true}`
   - Einzelnes Geraet / Sensor: `mcp__smarthome__zustand{name}`
   - Raeume: `mcp__smarthome__raeume`
   - Schalten: `mcp__smarthome_schalten__schalten{name, aktion: an|aus|umschalten, helligkeit?}`
     ("alle Lichter in der Kueche aus" = `{name: "Licht", raum: "Küche", art: "licht", aktion: "aus", alle: true}`)
   - Szene: `mcp__smarthome_schalten__szene{name}`
2. Das Ergebnis ist ein fertiger Satz: fast woertlich sprechen, nichts erfinden.
3. Meldet das Werkzeug "nicht eindeutig", die genannten Moeglichkeiten zur Auswahl stellen.

## Pitfalls
- Vor dem Schalten nichts behaupten; erst das Ergebnis sagt, ob es geklappt hat.
- Lehnt der Nutzer die Bestaetigung ab, ist nichts passiert.
- Ist kein System eingerichtet, auf die NuOrb-Verwaltung (Adresse + Token) hinweisen.
