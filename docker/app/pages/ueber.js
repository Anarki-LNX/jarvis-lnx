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
  };
  const DE = {
    back: "← Zur Verwaltung", title: "Über", h_models: "Sprachmodelle", h_stt: "Spracherkennung", h_voice: "Stimmen",
    th_voice: "Stimme", th_lic: "Lizenz", th_credit: "Aufnahmen · Basisstimme",
    voice_note: "Die Sprachausgabe entsteht auf diesem Server. Beide Stimmen sind CC0: frei nutzbar, auch kommerziell.",
    h_lic: "Lizenzen", lic_own: "Der eigene Code von {brand} steht unter der MIT-Lizenz. {brand} baut auf vielen Open-Source-Projekten und Modellen auf; jedes behält seine eigene Lizenz.",
    lic_link: "Komponenten von Dritten und ihre Lizenzen", lic_path: "Im Container:",
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
      if (v.data_url) cr.append(link(v.data_url, v.data), ` · ${v.base}`); else cr.textContent = "–";
    }
    $("licLink").href = d.licenses_url; $("licPath").textContent = d.licenses_path;
  }).catch(() => {});
})();
