// JARVIS LNX (Docker): Einrichtung – Sprache/Stimme, Gehirn (Ollama, Claude, beides), Modell-Downloads, weiter zum Koppeln.
(function () {
  const $ = (id) => document.getElementById(id);
  const EN = {
    back: "← Back to admin", title: "Setup", lead: "Three steps: language, brain, pair a device. Everything can be changed later in the admin panel.",
    h_status: "Status", h_lang: "1 · Name, language and voice", l_aname: "Assistant name (how you address it)", l_uname: "Your name (optional)", name_hint: "The wake word stays “Hey” plus the product name. You can also rename it in conversation: “From now on you are called …”.", l_lang: "Language", l_voice: "Voice", apply: "Apply",
    h_mode: "2 · Brain", m_local: "Local (Ollama)", m_local_d: "Only your Ollama. Nothing leaves your home. Free.",
    m_auto: "Both (automatic)", m_auto_d: "Ollama, and Claude when the PC is off.", m_remote: "Claude (API)",
    m_remote_d: "No PC of your own needed, costs per question.",
    h_ollama: "Ollama", l_url: "Address", probe: "Test connection", l_model: "Model", l_ctx: "Context (tokens)",
    ctx_hint: "Important: Hermes requires at least 64k tokens of context. Set OLLAMA_CONTEXT_LENGTH=65536 on the Ollama server or create a model variant with “PARAMETER num_ctx”, otherwise answers get cut off.",
    h_claude: "Claude", l_key: "Anthropic API key", l_remote: "Claude model",
    cost: "Cost: billed per token directly by Anthropic (console.anthropic.com). A short voice question costs about 0.1–0.5 cents with Haiku, a few cents with Sonnet. Set a spending limit there.",
    privacy: "Privacy: with Claude, conversation text is sent to Anthropic (USA). Audio always stays local.",
    save: "Save brain", skip: "Later", h_pair: "3 · Pair a device", pair_d: "Create a QR code for the JARVIS app or a code for a browser.",
    pair_go: "Go to “Pair device”",
  };
  const MSG = {
    de: { set: "Schlüssel gesetzt: ", none: "Noch kein Schlüssel hinterlegt.", saving: "Speichere … (Hermes startet neu, ~20 s)",
          ok: "Fertig. JARVIS denkt jetzt mit: ", probing: "Teste …", found: (v, n) => `Verbunden: Ollama ${v}, ${n} Modelle.`, err: "Fehler: ",
          noBrain: "⚠ Noch kein Gehirn eingerichtet – JARVIS kann noch nicht antworten.", brain: (m) => `✓ Gehirn eingerichtet (${m}).`,
          load: (s) => `Lade Sprachmodelle: ${s.item || ""} ${s.done_mb || 0} / ${s.total_mb || "?"} MB`, ready: "✓ Sprachmodelle bereit (Spracherkennung und Stimme).",
          langOk: "Übernommen.", dl: (v) => `Übernommen, Stimme ${v} wird geladen …`, modes: { local: "Lokal", auto: "Automatik", remote: "Claude" } },
    en: { set: "Key set: ", none: "No key stored yet.", saving: "Saving … (Hermes restarts, ~20 s)",
          ok: "Done. JARVIS now thinks with: ", probing: "Testing …", found: (v, n) => `Connected: Ollama ${v}, ${n} models.`, err: "Error: ",
          noBrain: "⚠ No brain configured yet – JARVIS cannot answer yet.", brain: (m) => `✓ Brain configured (${m}).`,
          load: (s) => `Downloading speech models: ${s.item || ""} ${s.done_mb || 0} / ${s.total_mb || "?"} MB`, ready: "✓ Speech models ready (recognition and voice).",
          langOk: "Applied.", dl: (v) => `Applied, downloading voice ${v} …`, modes: { local: "local", auto: "automatic", remote: "Claude" } },
  };
  let m = MSG.de, S = null;
  const api = async (path, body) => {
    const r = await fetch(path, body === undefined ? { cache: "no-store" } : {
      method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis": "1" }, body: JSON.stringify(body) });
    if (r.status === 401) { location.href = "/"; throw new Error("login"); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || r.status);
    return d;
  };
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
    } catch (e) { $("langMsg").className = "err"; $("langMsg").textContent = m.err + e.message; }
  });

  async function probe() {
    $("probeMsg").textContent = m.probing; $("probeMsg").className = "muted";
    try {
      const d = await api("/api/setup/ollama", { url: $("url").value.trim() });
      const cur = $("model").value || $("model").dataset.want || "";
      $("model").replaceChildren();
      for (const n of d.models) { const o = document.createElement("option"); o.value = o.textContent = n; $("model").append(o); }
      if (cur && d.models.includes(cur)) $("model").value = cur;
      $("probeMsg").textContent = m.found(d.version, d.models.length); $("probeMsg").className = "ok";
    } catch (e) { $("probeMsg").textContent = m.err + e.message; $("probeMsg").className = "err"; }
  }
  $("probe").addEventListener("click", probe);

  $("save").addEventListener("click", async () => {
    $("save").disabled = true; $("msg").className = "muted"; $("msg").textContent = m.saving;
    try {
      const d = await api("/api/setup/apply", { mode: mode(), ollama_url: $("url").value.trim(), ollama_model: $("model").value,
        context: Number($("ctx").value), anthropic_key: $("key").value.trim(), remote_model: $("remote").value });
      $("key").value = "";
      $("msg").className = "ok"; $("msg").textContent = m.ok + d.desc;
      $("brainState").className = "ok"; $("brainState").textContent = m.brain(m.modes[mode()]);
    } catch (e) { $("msg").className = "err"; $("msg").textContent = m.err + e.message; }
    $("save").disabled = false;
  });
  $("skip").addEventListener("click", () => { sessionStorage.setItem("jl.setupSkipped", "1"); location.href = "/"; });

  function showModels(x) {
    const st = $("modelState");
    if (x.stt_ready && x.voice_ready && x.state !== "loading") { st.className = "ok"; st.textContent = m.ready; $("bar").hidden = true; return false; }
    if (x.state === "error") { st.className = "err"; st.textContent = x.error; $("bar").hidden = true; return true; }
    st.className = "muted"; st.textContent = m.load(x);
    $("bar").hidden = !x.total_mb; $("barFill").style.width = (x.total_mb ? Math.min(100, 100 * x.done_mb / x.total_mb) : 0) + "%";
    return true;
  }
  async function pollModels() {
    try { if (showModels(await api("/api/setup/models"))) setTimeout(pollModels, 2000); } catch (e) { setTimeout(pollModels, 5000); }
  }

  api("/api/setup").then((s) => {
    S = s;
    if (s.lang === "en") {
      m = MSG.en; document.documentElement.lang = "en"; document.title = "JARVIS · Setup";
      document.querySelectorAll("[data-t]").forEach((el) => { if (EN[el.dataset.t]) el.textContent = EN[el.dataset.t]; });
    }
    $("lang").value = s.lang; voices(s.lang, s.voice);
    $("aname").value = s.assistant_name || ""; $("aname").placeholder = s.brand || "";
    $("uname").value = s.user_name || "";
    $("brainState").className = s.done ? "ok" : "warn";
    $("brainState").textContent = s.done ? m.brain(m.modes[s.brain] || s.brain) : m.noBrain;
    showModels(s.models || {}); pollModels();
    $("url").value = s.ollama_url || "";
    $("model").dataset.want = s.ollama_model || "";
    if (s.ollama_model) { const o = document.createElement("option"); o.value = o.textContent = s.ollama_model; $("model").replaceChildren(o); }
    $("keyState").textContent = s.anthropic_key ? m.set + s.anthropic_key : m.none;
    for (const [id, x] of Object.entries(s.claude_models || {})) {
      const o = document.createElement("option"); o.value = id; o.textContent = `${x.name} – ${x.hint}`; $("remote").append(o);
    }
    $("remote").value = s.remote_model || "claude-haiku-5-5";
    const want = s.done ? s.brain : (s.ollama_url ? (s.anthropic_key ? "auto" : "local") : (s.anthropic_key ? "remote" : "local"));
    const r = document.querySelector(`input[name="mode"][value="${want}"]`); if (r) r.checked = true;
    refresh();
    if (s.ollama_url) probe();
  }).catch(() => { location.href = "/"; });
})();
