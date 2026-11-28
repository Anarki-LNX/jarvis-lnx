// NuOrb (Docker): Verwaltungsseite „Wetter“. Ort einmalig suchen, Quelle wählen, optionale Schlüssel, Test.
// Alle Abfragen an Wetterdienste laufen auf dem Server (/api/weather/*), nie im Browser.
// Ausgabe nur über textContent (Server- und Nutzerwerte), Ereignisse nur über addEventListener (CSP ohne Inline).
(function () {
  const $ = (id) => document.getElementById(id);
  const I = window.NuI18n;
  const EN = {
    back: "← Back to admin", title: "Weather",
    lead: "Set your place once. {brand} then answers weather questions with current values, forecast and official warnings. All requests go from this server directly to the weather service.",
    h_place: "1 · Place", l_query: "Place or postcode", search: "Search",
    geo_note: "Place names: Open-Meteo Geocoding, location data based on GeoNames (CC BY 4.0). Postcodes: OpenStreetMap Nominatim, © OpenStreetMap contributors (ODbL). The search runs only now, not during normal use.",
    h_source: "2 · Source", l_provider: "Weather service", p_auto: "Automatic: German Weather Service in Germany, Open-Meteo elsewhere",
    p_dwd: "German Weather Service (DWD) via Bright Sky", p_om: "Open-Meteo", l_bsurl: "Own Bright Sky instance (optional)", save: "Save",
    dwd_note: "Quelle: Deutscher Wetterdienst (CC BY 4.0), via Bright Sky. Official warnings are read out unchanged.",
    l_omkey: "Open-Meteo API key (only for commercial use)",
    om_note: "Weather data by Open-Meteo.com (CC BY 4.0). The free Open-Meteo API may only be used non-commercially. Personal home automation counts as non-commercial.",
    h_wxm: "3 · WeatherXM station (optional)",
    wxm_note: "Hyperlocal measurements from a WeatherXM station near you, with your own WeatherXM Pro API key. Forecast and warnings still come from the German Weather Service. The terms of WeatherXM apply to your account.",
    l_wxmkey: "WeatherXM Pro API key", find: "Find stations", l_measure: "Measurements from", m_dwd: "Weather service (DWD or Open-Meteo)",
    m_wxm: "My WeatherXM station", h_test: "4 · Test", l_period: "Period", z_now: "Now", z_today: "Today", z_tomorrow: "Tomorrow",
    z_week: "Next days", z_warn: "Warnings", test: "Test", clear: "Delete place and keys",
  };
  const DE = {
    back: "← Zur Verwaltung", title: "Wetter",
    lead: "Einmal den Ort eintragen. Danach beantwortet {brand} Wetterfragen mit aktuellen Werten, Vorhersage und amtlichen Warnungen. Alle Abfragen gehen von diesem Server direkt an den Wetterdienst.",
    h_place: "1 · Ort", l_query: "Ort oder Postleitzahl", search: "Suchen",
    geo_note: "Ortsnamen: Open-Meteo Geocoding, Ortsdaten von GeoNames (CC BY 4.0). Postleitzahlen: OpenStreetMap Nominatim, © OpenStreetMap contributors (ODbL). Gesucht wird nur jetzt, nicht im normalen Betrieb.",
    h_source: "2 · Quelle", l_provider: "Wetterdienst", p_auto: "Automatisch: Deutscher Wetterdienst in Deutschland, sonst Open-Meteo",
    p_dwd: "Deutscher Wetterdienst (DWD) über Bright Sky", p_om: "Open-Meteo", l_bsurl: "Eigene Bright-Sky-Instanz (optional)", save: "Speichern",
    dwd_note: "Quelle: Deutscher Wetterdienst (CC BY 4.0), über Bright Sky. Amtliche Warnungen werden unverändert vorgelesen.",
    l_omkey: "Open-Meteo-API-Schlüssel (nur für kommerzielle Nutzung)",
    om_note: "Wetterdaten von Open-Meteo.com (CC BY 4.0). Die kostenlose Open-Meteo-API darf nur nicht-kommerziell genutzt werden. Private Hausautomation gilt als nicht-kommerziell.",
    h_wxm: "3 · WeatherXM-Station (optional)",
    wxm_note: "Hyperlokale Messwerte einer WeatherXM-Station in deiner Nähe, mit deinem eigenen WeatherXM-Pro-Schlüssel. Vorhersage und Warnungen kommen weiter vom Deutschen Wetterdienst. Für dein Konto gelten die Bedingungen von WeatherXM.",
    l_wxmkey: "WeatherXM-Pro-API-Schlüssel", find: "Stationen suchen", l_measure: "Messwerte von", m_dwd: "Wetterdienst (DWD oder Open-Meteo)",
    m_wxm: "Meine WeatherXM-Station", h_test: "4 · Test", l_period: "Zeitraum", z_now: "Jetzt", z_today: "Heute", z_tomorrow: "Morgen",
    z_week: "Nächste Tage", z_warn: "Warnungen", test: "Testen", clear: "Ort und Schlüssel löschen",
  };
  const M = {
    de: { none: "Noch kein Ort eingetragen.", now: "Ort: ", nohits: "Nichts gefunden. Anderen Namen oder die Postleitzahl versuchen.",
          saved: "Gespeichert.", station: "Nächste DWD-Station: ", km: " km entfernt", om: "Quelle: Open-Meteo (Modelldaten für den Ort).",
          keyNone: "Kein Schlüssel hinterlegt.", keySet: "Schlüssel: ", nostations: "Keine WeatherXM-Station in zehn Kilometern gefunden.",
          wxmSel: "Gewählte Station: ", sure: "Ort, Schlüssel und Zwischenspeicher wirklich löschen?", busy: "Einen Moment …",
          eff: { dwd: "Deutscher Wetterdienst", openmeteo: "Open-Meteo" } },
    en: { none: "No place set yet.", now: "Place: ", nohits: "Nothing found. Try another name or the postcode.",
          saved: "Saved.", station: "Nearest DWD station: ", km: " km away", om: "Source: Open-Meteo (model data for the place).",
          keyNone: "No key stored.", keySet: "Key: ", nostations: "No WeatherXM station found within ten kilometres.",
          wxmSel: "Chosen station: ", sure: "Really delete place, keys and cache?", busy: "One moment …",
          eff: { dwd: "German Weather Service", openmeteo: "Open-Meteo" } },
  };
  let m = M.en, st = null;

  const msg = (id, text, isErr) => { const el = $(id); el.textContent = text || ""; el.classList.toggle("ok", !!text && !isErr); };
  const fail = (id) => (e) => msg(id, I.tr(e.message), true);

  function render(s) {
    st = s;
    const p = s.place;
    $("placeNow").textContent = p ? m.now + [p.name, p.postcode, p.region].filter(Boolean).join(", ") : m.none;
    $("provider").value = s.provider || "auto";
    $("bsurl").value = s.brightsky_url || "";
    $("measure").value = s.measure || "dwd";
    $("omState").textContent = s.keys.openmeteo ? m.keySet + s.keys.openmeteo : m.keyNone;
    $("wxmState").textContent = (s.keys.wxm ? m.keySet + s.keys.wxm : m.keyNone) +
      (s.wxm_station ? " · " + m.wxmSel + s.wxm_station.name : "");
    for (const id of ["pSource", "pWxm", "pTest"]) $(id).hidden = !p;
    if (p) loadStation();
  }

  function loadStation() {
    $("station").textContent = m.busy;
    I.api("/api/weather/station").then((d) => {
      if (d.provider === "openmeteo") $("station").textContent = m.om;
      else if (d.station) $("station").textContent = m.station + d.station + ", " + String(d.distance_km).replace(".", I.lang === "de" ? "," : ".") + m.km;
      else $("station").textContent = d.error ? I.tr(d.error) : "";
    }).catch(fail("station"));
  }

  function choice(container, title, sub, onPick) {
    const lab = document.createElement("label"); lab.className = "choice";
    const inp = document.createElement("input"); inp.type = "radio"; inp.name = container.id;
    const b = document.createElement("b"); b.textContent = title;
    const s = document.createElement("span"); s.className = "muted"; s.textContent = sub;
    lab.append(inp, b, document.createElement("br"), s);
    inp.addEventListener("change", onPick);
    container.append(lab);
  }

  $("search").addEventListener("click", () => {
    const q = $("query").value.trim();
    msg("placeMsg", m.busy);
    $("results").replaceChildren();
    I.api("/api/weather/search", { query: q }).then((d) => {
      msg("placeMsg", d.results.length ? "" : m.nohits, !d.results.length);
      for (const r of d.results) {
        choice($("results"), [r.name, r.postcode].filter(Boolean).join(" "), [r.region, r.country_code].filter(Boolean).join(", "), () => {
          I.api("/api/weather/place", { place: r }).then((s) => { $("results").replaceChildren(); msg("placeMsg", m.saved); render(s); })
            .catch(fail("placeMsg"));
        });
      }
    }).catch(fail("placeMsg"));
  });
  $("query").addEventListener("keydown", (e) => { if (e.key === "Enter") $("search").click(); });

  $("saveSource").addEventListener("click", () => {
    I.api("/api/weather/options", { provider: $("provider").value, brightsky_url: $("bsurl").value })
      .then((s) => { msg("sourceMsg", m.saved); render(s); }).catch(fail("sourceMsg"));
  });
  $("saveOm").addEventListener("click", () => {
    I.api("/api/weather/keys", { openmeteo: $("omkey").value }).then((s) => { $("omkey").value = ""; msg("sourceMsg", m.saved); render(s); })
      .catch(fail("sourceMsg"));
  });
  $("saveWxm").addEventListener("click", () => {
    I.api("/api/weather/keys", { wxm: $("wxmkey").value }).then((s) => { $("wxmkey").value = ""; msg("wxmMsg", m.saved); render(s); })
      .catch(fail("wxmMsg"));
  });
  $("findWxm").addEventListener("click", () => {
    msg("wxmMsg", m.busy);
    $("wxmList").replaceChildren();
    I.api("/api/weather/wxm-stations", {}).then((d) => {
      msg("wxmMsg", d.stations.length ? "" : m.nostations, !d.stations.length);
      for (const s of d.stations) {
        choice($("wxmList"), s.name, String(s.distance_km).replace(".", I.lang === "de" ? "," : ".") + m.km, () => {
          I.api("/api/weather/options", { wxm_station: s }).then((r) => { msg("wxmMsg", m.saved); render(r); }).catch(fail("wxmMsg"));
        });
      }
    }).catch(fail("wxmMsg"));
  });
  $("saveMeasure").addEventListener("click", () => {
    I.api("/api/weather/options", { measure: $("measure").value }).then((s) => { msg("wxmMsg", m.saved); render(s); })
      .catch(fail("wxmMsg"));
  });
  $("test").addEventListener("click", () => {
    $("testOut").textContent = m.busy;
    I.api("/api/weather/test", { zeitraum: $("period").value })
      .then((d) => { $("testOut").textContent = d.text; $("testOut").classList.toggle("ok", !d.error); })
      .catch((e) => { $("testOut").textContent = I.tr(e.message); });
  });
  $("clear").addEventListener("click", () => {
    if (!window.confirm(m.sure)) return;
    I.api("/api/weather/clear", {}).then((s) => { $("testOut").textContent = ""; render(s); }).catch(fail("placeMsg"));
  });

  Promise.all([I.api("/api/about").catch(() => ({})), I.api("/api/weather")]).then(([about, s]) => {
    I.init(about, { en: EN, de: DE }, "title");
    m = M[I.lang] || M.en;
    render(s);
  }).catch(() => {});
})();
