// NuOrb (Docker): Verwaltungsseite „Werkzeuge“. Enger Standard oder erweiterte Werkzeuge von Hermes (S5/S6).
// Ausgabe nur über textContent, Ereignisse nur über addEventListener (CSP ohne Inline).
(function () {
  const $ = (id) => document.getElementById(id);
  const I = window.NuI18n;
  const EN = {
    back: "← Back to admin", title: "Tools", lead: "Which tools the language model may use when you talk to {brand}.",
    h_mode: "Tools of the assistant", narrow: "Standard (recommended)",
    narrow_d: "Web search, web pages, images, memory, reminders, skills and all {brand} tools (smart home, weather, name). No shell, no files, no browser.",
    extended: "Extended", extended_d: "Additionally shell commands, Python, reading and writing files, the browser and sub-agents.",
    warn: "Extended tools are a risk. A web page or a document can contain hidden instructions. With shell and file access the model can then read the passwords and keys of this server or reach devices in your home network. Only switch this on if you need it and know the risk.",
    save: "Save", h_rules: "Rules that always apply",
    rule_outside: "After the assistant has read outside content (web search, web page, file, image, an added MCP server), every action with an effect needs your confirmation on a card. This applies to the whole conversation.",
    rule_net: "Shell, Python and browser may not reach addresses in your home network. Only the addresses you entered for the brain, MCP servers and smart home are allowed.",
  };
  const DE = {
    back: "← Zur Verwaltung", title: "Werkzeuge", lead: "Welche Werkzeuge das Sprachmodell benutzen darf, wenn du mit {brand} sprichst.",
    h_mode: "Werkzeuge des Assistenten", narrow: "Standard (empfohlen)",
    narrow_d: "Websuche, Webseiten, Bilder, Gedächtnis, Erinnerungen, Skills und alle Werkzeuge von {brand} (Smart Home, Wetter, Name). Keine Shell, keine Dateien, kein Browser.",
    extended: "Erweitert", extended_d: "Zusätzlich Shell-Befehle, Python, Dateien lesen und schreiben, der Browser und Unteragenten.",
    warn: "Erweiterte Werkzeuge sind ein Risiko. Eine Webseite oder ein Dokument kann versteckte Anweisungen enthalten. Mit Shell- und Dateizugriff kann das Modell dann die Passwörter und Schlüssel dieses Servers lesen oder Geräte in deinem Heimnetz ansprechen. Nur einschalten, wenn du es brauchst und das Risiko kennst.",
    save: "Speichern", h_rules: "Regeln, die immer gelten",
    rule_outside: "Hat der Assistent fremde Inhalte gelesen (Websuche, Webseite, Datei, Bild, ein hinzugefügter MCP-Server), braucht jede Aktion mit Wirkung deine Bestätigung auf einer Karte. Das gilt für das ganze Gespräch.",
    rule_net: "Shell, Python und Browser dürfen keine Adressen in deinem Heimnetz ansprechen. Erlaubt sind nur die Adressen, die du für Gehirn, MCP-Server und Smart Home eingetragen hast.",
  };
  const M = {
    de: { saved: "Gespeichert. Hermes startet neu.", same: "Unverändert.", busy: "Einen Moment …",
          sure: "Erweiterte Werkzeuge wirklich einschalten? Lies bitte vorher den Hinweis unter der Auswahl." },
    en: { saved: "Saved. Hermes restarts.", same: "Unchanged.", busy: "One moment …",
          sure: "Really switch on extended tools? Please read the note below the choice first." },
  };
  let state = { mode: "narrow" }, m = M.en;
  const chosen = () => (document.querySelector('input[name="mode"]:checked') || {}).value || "narrow";
  const show = () => {
    for (const [id, v] of [["cNarrow", "narrow"], ["cExtended", "extended"]]) {
      const el = $(id); const on = chosen() === v;
      el.setAttribute("aria-checked", String(on));
    }
    $("warn").hidden = chosen() !== "extended";
  };
  document.querySelectorAll('input[name="mode"]').forEach((r) => r.addEventListener("change", show));

  I.api("/api/tools").then((d) => {
    I.init(d, { en: EN, de: DE }, "title");
    m = M[I.lang] || M.en;
    state = d;
    const r = document.querySelector(`input[name="mode"][value="${d.mode === "extended" ? "extended" : "narrow"}"]`);
    if (r) r.checked = true;
    show();
    if (d.notice) I.api("/api/tools", { notice_seen: true }).catch(() => {});
  }).catch((e) => { $("msg").textContent = String(e.message || e); });

  $("save").addEventListener("click", async () => {
    const mode = chosen();
    if (mode === state.mode) { $("msg").textContent = m.same; return; }
    if (mode === "extended" && !confirm(m.sure)) return;
    $("save").disabled = true; $("msg").textContent = m.busy;
    try {
      state = await I.api("/api/tools", { mode });
      $("msg").textContent = m.saved;
    } catch (e) { $("msg").textContent = I.tr(String(e.message || e)); }
    $("save").disabled = false;
  });
})();
