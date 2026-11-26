// NuOrb (Docker): Einrichtung – Name/Sprache/Stimme, Gehirn (Ollama, Claude, beides), Modell-Downloads, weiter zum Koppeln.
(function () {
  const $ = (id) => document.getElementById(id);
  const I = window.NuI18n;
  const EN = {
    back: "← Back to admin", title: "Setup", lead: "Three steps: language, brain, pair a device. Everything can be changed later in the admin panel.",
    h_status: "Status", h_lang: "1 · Name, language and voice", l_aname: "Assistant name (how you address it)", l_uname: "Your name (optional)",
    name_hint: "The wake word stays “Hey {brand}”. You can also rename the assistant in conversation: “From now on you are called …”.",
    l_lang: "Assistant language", l_voice: "Voice", apply: "Apply",
    h_mode: "2 · Brain", m_local: "Local (Ollama)", m_local_d: "Only your Ollama. Nothing leaves your home. Free.",
    m_auto: "Both (automatic)", m_auto_d: "Ollama, and Claude when the PC is off.", m_remote: "Claude (API)",
    m_remote_d: "No PC of your own needed, costs per question.",
    h_ollama: "Ollama", l_url: "Address", probe: "Test connection",
    url_hint: "IP address of the computer running Ollama (or its hostname, e.g. http://ollama.local:11434). Use the IP if the name doesn't resolve. Ollama on this same machine: use this machine's IP too (start Ollama with OLLAMA_HOST=0.0.0.0).", l_model: "Model", l_ctx: "Context (tokens)",
    ctx_hint: "Important: Hermes requires at least 64k tokens of context. Set OLLAMA_CONTEXT_LENGTH=65536 on the Ollama server or create a model variant with “PARAMETER num_ctx”, otherwise answers get cut off.",
    h_claude: "Claude", l_key: "Anthropic API key", l_remote: "Claude model",
    cost: "Cost: billed per token directly by Anthropic (console.anthropic.com). A short voice question costs about 0.1–0.5 cents with Haiku, a few cents with Sonnet. Set a spending limit there.",
    privacy: "Privacy: with Claude, conversation text is sent to Anthropic (USA). Audio always stays local.",
    save: "Save brain", skip: "Later", h_pair: "3 · Pair a device", pair_d: "Create a QR code for the {brand} app or a code for a browser.",
    pair_go: "Go to “Pair device”",
  };
  const DE = {
    back: "← Zur Verwaltung", title: "Einrichtung", lead: "Drei Schritte: Sprache, Gehirn, Gerät koppeln. Alles lässt sich später in der Verwaltung ändern.",
    h_status: "Zustand", h_lang: "1 · Name, Sprache und Stimme", l_aname: "Name des Assistenten (so sprichst du ihn an)", l_uname: "Dein Name (optional)",
    name_hint: "Das Weckwort bleibt „Hey {brand}“. Den Namen kannst du auch im Gespräch ändern: „Ab jetzt heißt du …“.",
    l_lang: "Sprache des Assistenten", l_voice: "Stimme", apply: "Übernehmen",
    h_mode: "2 · Gehirn", m_local: "Lokal (Ollama)", m_local_d: "Nur dein Ollama. Nichts verlässt das Haus. Kostenlos.",
    m_auto: "Beides (Automatik)", m_auto_d: "Ollama, und Claude, wenn der PC aus ist.", m_remote: "Claude (API)",
    m_remote_d: "Kein eigener PC nötig, kostet pro Frage.",
    h_ollama: "Ollama", l_url: "Adresse", probe: "Verbindung testen",
    url_hint: "IP-Adresse des Rechners, auf dem Ollama läuft (oder sein Name, z. B. http://ollama.local:11434). Löst der Name nicht auf, nimm die IP. Ollama auf demselben Rechner wie NuOrb: ebenfalls dessen IP (Ollama mit OLLAMA_HOST=0.0.0.0 starten).", l_model: "Modell", l_ctx: "Kontext (Token)",
    ctx_hint: "Wichtig: Hermes verlangt mindestens 64k Token Kontext. Setze am Ollama-Server OLLAMA_CONTEXT_LENGTH=65536 oder lege eine Modell-Variante mit „PARAMETER num_ctx“ an, sonst werden Antworten abgeschnitten.",
    h_claude: "Claude", l_key: "Anthropic-API-Schlüssel", l_remote: "Claude-Modell",
    cost: "Kosten: Abrechnung pro Token direkt bei Anthropic (console.anthropic.com). Eine kurze Sprachfrage kostet mit Haiku etwa 0,1–0,5 Cent, mit Sonnet einige Cent. Lege dort ein Ausgabenlimit fest.",
    privacy: "Datenschutz: Bei Claude gehen die Gesprächstexte an Anthropic (USA). Audio bleibt immer lokal.",
    save: "Gehirn speichern", skip: "Später", h_pair: "3 · Gerät koppeln", pair_d: "Erzeuge einen QR-Code für die {brand}-App oder einen Code für den Browser.",
    pair_go: "Zu „Gerät koppeln“",
  };
  const MSG = {
    de: { set: "Schlüssel gesetzt: ", none: "Noch kein Schlüssel hinterlegt.", saving: "Speichere … (Hermes startet neu, ~20 s)",
          ok: "Fertig. {brand} denkt jetzt mit: ", probing: "Teste …", found: (v, n) => `Verbunden: Ollama ${v}, ${n} Modelle.`, err: "Fehler: ",
          noBrain: "⚠ Noch kein Gehirn eingerichtet – {brand} kann noch nicht antworten.", brain: (m) => `✓ Gehirn eingerichtet (${m}).`,
          load: (s) => s.total_mb ? `Lade Sprachmodelle: ${s.item || ""} ${s.done_mb || 0} / ${s.total_mb} MB` : `Verbinde für den Download der Sprachmodelle${s.item ? " (" + s.item + ")" : ""} …`, ready: "✓ Sprachmodelle bereit (Spracherkennung und Stimme).",
          offline: "Der Container hat keine Internetverbindung: Die Sprachmodelle (~530 MB) konnten nicht geladen werden. Neuer Versuch läuft automatisch. Häufigste Ursache ist die Firewall des Rechners (ufw: „sudo ufw default allow routed && sudo ufw reload“), sonst DNS oder Proxy.",
          fw: "Firewall am Ollama-Rechner? Port 11434 für Docker freigeben (172.16.0.0/12), z. B. sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp.",
          langOk: "Übernommen.", dl: (v) => `Übernommen, Stimme ${v} wird geladen …`, modes: { local: "Lokal", auto: "Automatik", remote: "Claude" } },
    en: { set: "Key set: ", none: "No key stored yet.", saving: "Saving … (Hermes restarts, ~20 s)",
          ok: "Done. {brand} now thinks with: ", probing: "Testing …", found: (v, n) => `Connected: Ollama ${v}, ${n} models.`, err: "Error: ",
          noBrain: "⚠ No brain configured yet – {brand} cannot answer yet.", brain: (m) => `✓ Brain configured (${m}).`,
          load: (s) => s.total_mb ? `Downloading speech models: ${s.item || ""} ${s.done_mb || 0} / ${s.total_mb} MB` : `Connecting to download the speech models${s.item ? " (" + s.item + ")" : ""} …`, ready: "✓ Speech models ready (recognition and voice).",
          offline: "The container has no internet connection: the speech models (~530 MB) could not be downloaded. Retrying automatically. Most common cause is the host firewall (ufw: “sudo ufw default allow routed && sudo ufw reload”), otherwise DNS or proxy.",
          fw: "Firewall on the Ollama machine? Allow port 11434 from Docker (172.16.0.0/12), e.g. sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp.",
          langOk: "Applied.", dl: (v) => `Applied, downloading voice ${v} …`, modes: { local: "local", auto: "automatic", remote: "Claude" } },
  };
  let m = MSG.en, S = null;
  const api = I.api;
  function mode() { return (document.querySelector('input[name="mode"]:checked') || {}).value || "local"; }
  function refresh() {
    document.querySelectorAll(".choice").forEach((c) => c.setAttribute("aria-checked", String(c.dataset.mode === mode())));
    $("pOllama").hidden = mode() === "remote";
    $("pClaude").hidden = mode() === "local";
  }
  document.querySelectorAll('input[name="mode"]').forEach((i) => i.addEventListener("change", refresh));

  function voices(lang, cur) {
    $("voice").replaceChildren();
    const list = (S.voice_choices || {})[lang] || [];
    for (const [id, label] of list) {
      const o = document.createElement("option"); o.value = id;
      o.textContent = label + ((S.voices_installed || []).includes(id) ? " ✓" : ""); $("voice").append(o);
    }
    if (cur && list.some(([id]) => id === cur)) $("voice").value = cur;
  }
  $("lang").addEventListener("change", () => voices($("lang").value));
  $("saveLang").addEventListener("click", async () => {
    try {
      await api("/api/assistant", { assistant_name: $("aname").value.trim(), user_name: $("uname").value.trim() });
      const d = await api("/api/setup/language", { lang: $("lang").value, voice: $("voice").value });
      $("langMsg").className = "ok"; $("langMsg").textContent = d.downloading ? m.dl(d.downloading) : m.langOk;
      setTimeout(() => location.reload(), d.downloading ? 1500 : 800);
    } catch (e) { $("langMsg").className = "err"; $("langMsg").textContent = m.err + I.tr(e.message); }
  });

  async function probe() {
    $("probeMsg").textContent = m.probing; $("probeMsg").className = "muted";
    try {
      const d = await api("/api/setup/ollama", { url: $("url").value.trim() });
      const cur = $("model").value || $("model").dataset.want || "";
      $("model").replaceChildren();
      for (const n of d.models) { const o = document.createElement("option"); o.value = o.textContent = n; $("model").append(o); }
      if (cur && d.models.includes(cur)) $("model").value = cur;
      if (d.url) $("url").value = d.url;   // vom Server vervollständigt (Schema, Port 11434, ohne /v1)
      $("probeMsg").textContent = m.found(d.version, d.models.length) + (d.warn ? " ⚠ " + I.tr(d.warn) : "");
      $("probeMsg").className = d.warn ? "warn" : "ok";
    } catch (e) {
      const zeit = /timeout|timed out|ConnectError/i.test(e.message);   // Firewall am Ollama-Rechner blockt das Docker-Netz
      $("probeMsg").textContent = m.err + I.tr(e.message) + (zeit ? " " + m.fw : ""); $("probeMsg").className = "err";
    }
  }
  $("probe").addEventListener("click", probe);

  $("save").addEventListener("click", async () => {
    $("save").disabled = true; $("msg").className = "muted"; $("msg").textContent = m.saving;
    try {
      const d = await api("/api/setup/apply", { mode: mode(), ollama_url: $("url").value.trim(), ollama_model: $("model").value,
        context: Number($("ctx").value), anthropic_key: $("key").value.trim(), remote_model: $("remote").value });
      $("key").value = "";
      $("msg").className = "ok"; $("msg").textContent = I.fmt(m.ok) + I.tr(d.desc);
      $("brainState").className = "ok"; $("brainState").textContent = m.brain(m.modes[mode()]);
    } catch (e) { $("msg").className = "err"; $("msg").textContent = m.err + I.tr(e.message); }
    $("save").disabled = false;
  });
  $("skip").addEventListener("click", () => { sessionStorage.setItem("jl.setupSkipped", "1"); location.href = "/"; });

  function showModels(x) {
    const st = $("modelState");
    if (x.stt_ready && x.voice_ready && x.state !== "loading") { st.className = "ok"; st.textContent = m.ready; $("bar").hidden = true; return false; }
    if (x.state === "error") { st.className = "err"; st.textContent = x.error_code === "offline" ? m.offline : I.tr(x.error); $("bar").hidden = true; return true; }
    st.className = "muted"; st.textContent = m.load(x);
    $("bar").hidden = !x.total_mb; $("barFill").style.width = (x.total_mb ? Math.min(100, 100 * x.done_mb / x.total_mb) : 0) + "%";
    return true;
  }
  async function pollModels() {
    try { if (showModels(await api("/api/setup/models"))) setTimeout(pollModels, 2000); } catch (e) { setTimeout(pollModels, 5000); }
  }

  api("/api/setup").then((s) => {
    S = s;
    I.init(s, { en: EN, de: DE }, "title");
    m = MSG[I.lang];
    $("lang").value = s.lang; voices(s.lang, s.voice);
    $("aname").value = s.assistant_name || ""; $("aname").placeholder = s.brand || "";
    $("uname").value = s.user_name || "";
    $("brainState").className = s.done ? "ok" : "warn";
    $("brainState").textContent = s.done ? m.brain(m.modes[s.brain] || s.brain) : I.fmt(m.noBrain);
    showModels(s.models || {}); pollModels();
    $("url").value = s.ollama_url || "";
    $("model").dataset.want = s.ollama_model || "";
    if (s.ollama_model) { const o = document.createElement("option"); o.value = o.textContent = s.ollama_model; $("model").replaceChildren(o); }
    $("keyState").textContent = s.anthropic_key ? m.set + s.anthropic_key : m.none;
    for (const [id, x] of Object.entries(s.claude_models || {})) {
      const o = document.createElement("option"); o.value = id; o.textContent = `${x.name} – ${I.tr(x.hint)}`; $("remote").append(o);
    }
    $("remote").value = s.remote_model || "claude-haiku-5-5";
    const want = s.done ? s.brain : (s.ollama_url ? (s.anthropic_key ? "auto" : "local") : (s.anthropic_key ? "remote" : "local"));
    const r = document.querySelector(`input[name="mode"][value="${want}"]`); if (r) r.checked = true;
    refresh();
    if (s.ollama_url) probe();
  }).catch(() => { location.href = "/"; });
})();
