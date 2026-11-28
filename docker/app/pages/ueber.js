// NuOrb (Docker): „Über“ – Version, Sprachmodelle mit Lizenz und Namensnennung (Parakeet CC-BY-4.0, Stimmen CC0).
(function () {
  const $ = (id) => document.getElementById(id);
  const I = window.NuI18n;
  const EN = {
    back: "← Back to admin", title: "About", h_models: "Speech models", h_stt: "Speech recognition", h_voice: "Voices",
    th_voice: "Voice", th_lic: "License", th_credit: "Recordings · base voice",
    voice_note: "Speech is generated on this server. Both voices are CC0: free to use, also commercially.",
    h_lic: "Licenses", lic_own: "{brand}'s own code is under the MIT license. It builds on many open-source projects and models; each keeps its own license.",
    lic_link: "Third-party components and licenses", lic_path: "In the container:",
    h_update: "Updates", upd_auto: "Check for new versions automatically (at most every 6 hours)",
    upd_note: "The check is a single request from this server to github.com (the newest NuOrb release, nothing else is sent apart from the usual connection data). Switched off here, only the button checks. NUORB_UPDATE_CHECK=0 in the .env switches it off completely.",
    h_weather: "Weather data", th_source: "Source", th_notice: "Notice",
    weather_note: "The built-in weather asks these services directly from this server. Official warnings of the German Weather Service are passed on unchanged.",
  };
  const DE = {
    back: "← Zur Verwaltung", title: "Über", h_models: "Sprachmodelle", h_stt: "Spracherkennung", h_voice: "Stimmen",
    th_voice: "Stimme", th_lic: "Lizenz", th_credit: "Aufnahmen · Basisstimme",
    voice_note: "Die Sprachausgabe entsteht auf diesem Server. Beide Stimmen sind CC0: frei nutzbar, auch kommerziell.",
    h_lic: "Lizenzen", lic_own: "Der eigene Code von {brand} steht unter der MIT-Lizenz. {brand} baut auf vielen Open-Source-Projekten und Modellen auf; jedes behält seine eigene Lizenz.",
    lic_link: "Komponenten von Dritten und ihre Lizenzen", lic_path: "Im Container:",
    h_update: "Updates", upd_auto: "Automatisch nach neuen Versionen suchen (höchstens alle 6 Stunden)",
    upd_note: "Die Prüfung ist ein einziger Abruf dieses Servers bei github.com (das neueste NuOrb-Release, außer den üblichen Verbindungsdaten wird nichts gesendet). Hier ausgeschaltet prüft nur noch der Knopf. NUORB_UPDATE_CHECK=0 in der .env schaltet sie ganz ab.",
    h_weather: "Wetterdaten", th_source: "Quelle", th_notice: "Hinweis",
    weather_note: "Das eingebaute Wetter fragt diese Dienste direkt von diesem Server aus ab. Amtliche Warnungen des Deutschen Wetterdienstes werden unverändert weitergegeben.",
  };
  const M = {
    de: { active: "aktiv", lang: { de: "Deutsch", en: "Englisch" }, ready: "geladen", notReady: "wird noch geladen",
          lic: "Lizenz", conv: "int8-ONNX-Export von" },
    en: { active: "active", lang: { de: "German", en: "English" }, ready: "loaded", notReady: "still loading",
          lic: "license", conv: "int8 ONNX export by" },
  };
  const link = (href, text) => { const a = document.createElement("a"); a.href = href; a.textContent = text; a.target = "_blank"; a.rel = "noopener"; return a; };

  I.api("/api/about").then((d) => {
    I.init(d, { en: EN, de: DE }, "title");
    const m = M[I.lang] || M.en;
    $("server").textContent = d.server;
    const s = d.stt, p = $("stt");
    p.replaceChildren(link(s.url, s.name), `, ${m.lic} `, link(s.license_url, s.license), `. ${m.conv} `,
                      link(s.conversion_url, "k2-fsa/sherpa-onnx"), ". ");
    const st = document.createElement("span"); st.className = "muted"; st.textContent = `(${s.ready ? m.ready : m.notReady})`; p.append(st);
    const tb = $("voices"); tb.replaceChildren();
    for (const v of d.voices) {
      const tr = tb.insertRow();
      const c = tr.insertCell(); c.textContent = `${v.name} (${m.lang[v.lang] || v.lang})`;
      if (v.active) { const b = document.createElement("strong"); b.textContent = ` · ${m.active}`; c.append(b); }
      const mono = document.createElement("div"); mono.className = "mono muted"; mono.textContent = v.id; c.append(mono);
      tr.insertCell().textContent = v.license || "?";
      const cr = tr.insertCell();
      if (v.data_url) cr.append(link(v.data_url, v.data), ` · ${v.base}`); else cr.textContent = "·";
    }
    const wb = $("weather"); wb.replaceChildren();
    for (const w of d.weather || []) {
      const tr = wb.insertRow();
      tr.insertCell().append(link(w.url, w.name));
      tr.insertCell().append(link(w.license_url, w.license));
      tr.insertCell().textContent = w.notice;
    }
    $("pWeather").hidden = !(d.weather || []).length;
    $("licLink").href = d.licenses_url; $("licPath").textContent = d.licenses_path;
    I.api("/api/update").then((u) => {
      const box = $("updAuto");
      box.checked = !!u.auto; box.disabled = !u.enabled;
      if (!u.enabled) $("updMsg").textContent = I.lang === "de" ? "Mit NUORB_UPDATE_CHECK=0 abgeschaltet." : "Switched off with NUORB_UPDATE_CHECK=0.";
      box.addEventListener("change", async () => {
        try { await I.api("/api/update", { auto: box.checked }); $("updMsg").textContent = I.lang === "de" ? "Gespeichert." : "Saved."; }
        catch (e) { box.checked = !box.checked; $("updMsg").textContent = I.tr(String(e.message || e)); }
      });
    }).catch(() => { $("pUpdate").hidden = true; });
  }).catch(() => {});
})();
