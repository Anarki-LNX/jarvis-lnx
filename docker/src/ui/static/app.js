/* NuOrb – Oberflaechenlogik: Zustaende, Push-to-Talk, Hermes-Run-Stream, satzweise TTS, Approvals. */
(function () {
  "use strict";
  // Oberflaechentexte ueber t(deText, vars): Deutsch unveraendert, Englisch aus i18n-en.js (siehe i18n.js)
  const t = (s, v) => (window.I18N ? window.I18N.t(s, v) : v ? String(s).replace(/\{(\w+)\}/g, (m, k) => (v[k] != null ? String(v[k]) : m)) : s);
  const DE = !window.I18N || window.I18N.lang === "de"; // lokale Sprachbefehle (deutsche Muster) nur auf Deutsch
  const LOC = DE ? "de-DE" : "en-GB";
  const $ = (id) => document.getElementById(id);
  const VERSION = "2026-11-25.55";
  // Kurzes Client-Log ins Server-Journal (Kiosk hat keine JS-Konsole)
  function clog(msg) {
    try { fetch("/api/clientlog", { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
      body: JSON.stringify({ v: VERSION, msg: String(msg).slice(0, 400) }) }).catch(() => {}); } catch (e) { /* egal */ }
  }
  window.addEventListener("error", (e) => clog("JS-Fehler: " + e.message + " @" + (e.filename || "").split("/").pop() + ":" + e.lineno));
  window.addEventListener("unhandledrejection", (e) => clog("Promise-Fehler: " + (e.reason && (e.reason.message || e.reason))));
  clog("geladen (build " + (document.documentElement.dataset.build || "?") + "): " + navigator.userAgent + " viewport " + innerWidth + "x" + innerHeight + " dpr " + devicePixelRatio);
  const app = $("app");
  const els = {
    stateLabel: $("stateLabel"), stateSub: $("stateSub"), convo: $("convo"), ptt: $("ptt"), pttHint: $("pttHint"),
    pttLevel: $("pttLevel"), chipBrain: $("chipBrain"), chipLink: $("chipLink"), clockMini: $("clockMini"),
    heroTime: $("heroTime"), heroDate: $("heroDate"), heroGreet: $("heroGreet"), jobs: $("jobsList"), notes: $("notesList"),
    toast: $("toast"),
  };
  const LABEL = {
    idle: [t("Bereit"), ""], listening: [t("Ich höre zu"), ""], transcribing: [t("Verstehe"), ""],
    thinking: [t("Denke nach"), ""], speaking: [t("Spreche"), ""], offline: [t("Gehirn offline"), t("Der PC mit dem Sprachmodell ist aus.")],
    error: [t("Störung"), ""],
  };

  // ------------------------------------------------------------------ Einstellungen
  const store = {
    get(k, d) { try { const v = localStorage.getItem("nuorb." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("nuorb." + k, JSON.stringify(v)); } catch (e) { /* egal */ } },
  };
  const opts = { voice: store.get("voice", true), calm: store.get("calm", false), earcons: store.get("earcons", true), micviz: store.get("micviz", true),
    follow: true, followTimeout: 8 }; // follow/followTimeout kommen aus ui.json (follow_up, follow_up_timeout_s) ueber /api/status
  // Android-App NuOrb (Sitzung android-app): WebView laedt den Server direkt, Bruecke window.NuOrbAndroid
  // (ab App 1.3.3; aeltere Fassungen: window.NuOrbAndroid, dasselbe Objekt).
  // Vertrag: Wake lokal (getWake/setWake, Ereignis „nuorb-wake“), Zustand an native (state), kein /api/wake, kein Vollbild.
  const ANDROID = !!(window.NuOrbAndroid || window.NuOrbAndroid) || new URLSearchParams(location.search).get("client") === "android"; // qp kommt erst weiter unten
  const NATIVE = window.NuOrbAndroid || window.NuOrbAndroid || null;
  let lastNative = "";
  function nativeState() {
    if (!NATIVE || typeof NATIVE.state !== "function") return;
    const card = !$("approvalBackdrop").hidden, st = card ? "card" : S.state;
    if (st !== lastNative) { lastNative = st; try { NATIVE.state(st); } catch (e) { /* egal */ } }
  }
  const CONV = { active: false, rounds: 0, lastAt: 0, n: 0, timer: null, prompted: false }; // Gespraechsmodus (siehe convCheck)
  const qp = new URLSearchParams(location.search);
  if (qp.get("micviz") === "0") opts.micviz = false;
  if (qp.get("echo") === "0") opts.echoOff = true;

  // ------------------------------------------------------------------ Zustand
  const S = {
    state: "idle", brain: null, link: null, busy: false, session: store.get("session", null), sessionDay: store.get("sessionDay", null),
    run: null, abort: null, lastActivity: Date.now(), approval: null, features: {},
  };
  // Gespraechskontext haelt einen Tag; danach frische Sitzung
  const today = new Date().toISOString().slice(0, 10);
  // SESSION_GEN erhoehen, wenn Hermes neue Werkzeuge bekommt (Werkzeugliste ist pro Sitzung eingefroren)
  const SESSION_GEN = "2026-11-24-geraet-3";
  if (S.sessionDay !== today || store.get("sessionGen", "") !== SESSION_GEN) { S.session = null; store.set("session", null); store.set("sessionGen", SESSION_GEN); }

  function setState(st, sub) {
    S.state = st;
    app.dataset.state = st;
    if (NATIVE) setTimeout(nativeState, 0);
    const [l, s] = LABEL[st] || [st, ""];
    els.stateLabel.textContent = l;
    els.stateSub.textContent = sub !== undefined ? sub : s;
    Orb.set({ state: st === "transcribing" ? "thinking" : st });
    app.dataset.busy = String(["transcribing", "thinking", "speaking"].includes(st));
    els.pttHint.textContent = st === "listening" ? (app.dataset.latched === "true" ? t("Sprich einfach · Tippen sendet sofort") : t("Loslassen zum Senden"))
      : app.dataset.busy === "true" ? t("Tippen zum Unterbrechen") : st === "offline" ? (S.link === false ? "Offline" : t("Gehirn offline · „wechsel auf Sonnet“")) : t("Tippen zum Sprechen");
  }
  function restingState() {
    if (S.brain === false || S.link === false) setState("offline", S.link === false ? t("Keine Verbindung zum Server.") : undefined);
    else setState("idle", "");
  }
  function view(v) { app.dataset.view = v; }

  function toast(msg, ms = 2600) {
    els.toast.textContent = msg; els.toast.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(() => els.toast.classList.remove("show"), ms);
  }

  // ------------------------------------------------------------------ Gespraechskarten
  function card(kind, text) {
    const d = document.createElement("div");
    d.className = "msg " + kind; d.textContent = text;
    els.convo.appendChild(d);
    while (els.convo.children.length > 24) els.convo.firstElementChild.remove();
    els.convo.scrollTop = els.convo.scrollHeight;
    view("talk"); S.lastActivity = Date.now();
    return d;
  }
  function toolChip(name, preview) {
    const d = document.createElement("div"); d.className = "tool";
    const i = document.createElement("i"); const s = document.createElement("span");
    s.textContent = TOOLNAME(name) + (preview ? " · " + preview : "");
    d.append(i, s); els.convo.appendChild(d); els.convo.scrollTop = els.convo.scrollHeight;
    return d;
  }
  const TOOLNAME = (n) => ({ terminal: "Terminal", read_file: t("Datei lesen"), write_file: t("Datei schreiben"), memory: t("Gedächtnis"),
    web_search: t("Websuche"), execute_code: "Code", cronjob: t("Zeitplan"), browser_exec: "Browser", patch: t("Datei ändern"),
    search_files: t("Suche"), todo: t("Aufgaben"), skill_view: t("Fähigkeit"), delegate_task: t("Unteragent"),
    mcp_claude_fragen: t("Claude fragen"), mcp_claude_auftrag: t("Claude-Auftrag"), mcp_claude_rueckgaengig: t("Claude: rückgängig"),
    mcp_claude_aenderungen: t("Claude: Änderungen"), mcp__geraet__anfordern: t("Gerät") }[n] ||
    (n && /^mcp_+claude_+/.test(n) ? "Claude · " + n.replace(/^mcp_+claude_+/, "") : n && /^mcp__/.test(n) ? n.slice(5).replace(/__/g, " · ") : n) || t("Werkzeug"));

  // ------------------------------------------------------------------ Uhr, Begruessung, Widgets
  const fmtTime = new Intl.DateTimeFormat(LOC, { hour: "2-digit", minute: "2-digit" });
  const fmtDate = new Intl.DateTimeFormat(LOC, { weekday: "long", day: "numeric", month: "long" });
  function greeting(h) {
    if (h < 5) return t("Späte Stunde. Ich bin wach.");
    if (h < 11) return t("Guten Morgen.");
    if (h < 14) return t("Mahlzeit. Was steht an?");
    if (h < 18) return t("Guten Tag. Zu Diensten.");
    if (h < 22) return t("Guten Abend.");
    return t("Noch wach? Ich auch.");
  }
  function tick() {
    const d = new Date(), hm = fmtTime.format(d);
    els.clockMini.textContent = hm; els.heroTime.textContent = hm;
    els.heroDate.textContent = fmtDate.format(d);
    els.heroGreet.textContent = S.brain === false ? t("Gehirn schläft. Basis läuft.") : greeting(d.getHours());
    // nach 90 s Ruhe zurueck zum Dashboard
    if (app.dataset.view === "talk" && !S.busy && S.state !== "listening" && !S.approval && Date.now() - S.lastActivity > 90000) view("home");
  }
  function relWhen(iso) {
    if (!iso) return "";
    const d = new Date(iso); if (isNaN(d)) return String(iso);
    const now = new Date(), days = Math.round((new Date(d.toDateString()) - new Date(now.toDateString())) / 864e5);
    const day = days === 0 ? t("Heute") : days === 1 ? t("Morgen") : days === 2 ? t("Übermorgen") : new Intl.DateTimeFormat(LOC, { weekday: "short", day: "numeric", month: "short" }).format(d);
    return day + ", " + fmtTime.format(d);
  }
  function fillList(ul, items, empty) {
    ul.replaceChildren();
    if (!items.length) { const li = document.createElement("li"); li.className = "muted"; li.textContent = empty; ul.appendChild(li); return; }
    for (const it of items) {
      const li = document.createElement("li");
      if (it.when) { const w = document.createElement("span"); w.className = "when"; w.textContent = it.when; li.appendChild(w); }
      li.appendChild(document.createTextNode(it.text)); ul.appendChild(li);
    }
  }
  async function loadWidgets() {
    try {
      const r = await fetch("/api/widgets"); const d = await r.json();
      fillList(els.jobs, (d.jobs || []).slice(0, 2).map((j) => ({ when: relWhen(j.next) || j.schedule || "", text: j.name })),
        t("Nichts geplant. Sag z. B. „Erinnere mich morgen um acht …“"));
      fillList(els.notes, (d.notes || []).slice(0, 2).map((n) => ({ text: n })), t("Noch leer. Sag „Merk dir …“"));
    } catch (e) {
      fillList(els.jobs, [], t("Keine Daten von Hermes.")); fillList(els.notes, [], t("Keine Daten von Hermes."));
    }
  }

  // ------------------------------------------------------------------ Status
  // Chip-Text zum Gehirn-Schalter (nuorb-admin): „Lokal · Gemma“, „Auto · Claude“, „Remote · Claude“
  function modelShort(m, effective) {
    if (!m) return effective === "remote" ? "Claude" : "";
    const x = m.toLowerCase();
    const cm = x.match(/claude-(haiku|sonnet|opus)-(\d+)-(\d+)/);
    if (cm) return cm[1][0].toUpperCase() + cm[1].slice(1) + " " + cm[2] + "." + cm[3];
    return x.includes("claude") ? "Claude" : x.includes("gemma") ? "Gemma" : x.includes("gpt-oss") ? "GPT-OSS" : m.split(/[:/]/)[0].slice(0, 14);
  }
  function brainLabel(d) {
    const mode = d.brain_mode || "local", eff = d.brain_effective || "local";
    const name = eff === "remote" ? modelShort(d.brain_model_remote || (d.brain_model && /claude/i.test(d.brain_model) ? d.brain_model : null), "remote")
      : modelShort(d.brain_model && !/claude/i.test(d.brain_model) ? d.brain_model : null, "local");
    const head = mode === "auto" ? "Auto" : mode === "remote" ? "Remote" : t("Lokal");
    return name ? head + " · " + name : (mode === "local" ? t("Gehirn online") : head);
  }
  async function pollStatus() {
    let d = null;
    try {
      const ctl = new AbortController(); const to = setTimeout(() => ctl.abort(), 4000);
      const r = await fetch("/api/status", { signal: ctl.signal }); clearTimeout(to);
      if (!r.ok) throw new Error("HTTP " + r.status); // ueber nuorb-shell: 503, wenn nuorb weg ist
      d = await r.json(); S.link = true;
    } catch (e) { S.link = false; }
    const demo = !!(d && d.mode === "demo");
    const remote = !!(d && d.brain_effective === "remote");
    const brain = d ? (demo ? true : (d.brain_ok !== undefined ? !!d.brain_ok : !!(d.brain && d.hermes))) : null;
    const changed = brain !== S.brain;
    S.brain = d ? brain : S.brain;
    if (!DEV.st) els.chipLink.dataset.ok = String(S.link);
    if (DEV.st) renderDevice(); else renderOffline();
    els.chipBrain.dataset.ok = d ? (demo ? "demo" : !brain ? "false" : remote ? "remote" : "true") : "unknown";
    els.chipBrain.querySelector(".chip-label").textContent = !d ? (S.link === false ? "Offline" : t("Gehirn ?")) : demo ? t("Demo-Modus") : brain ? brainLabel(d) : (!d.hermes ? t("Hermes aus") : t("Gehirn offline"));
    LABEL.offline[1] = d && !d.hermes ? t("Hermes-Dienst antwortet nicht.") : t("Der PC mit dem Sprachmodell ist aus.");
    $("privacyRow").hidden = !(d && remote && !demo);
    if (d && remote !== S._remote && S._remote !== undefined && !demo) toast(remote ? t("Gehirn: Claude (Remote). Text geht an Anthropic, Audio bleibt lokal.") : t("Gehirn: wieder lokal."));
    S._remote = d ? remote : S._remote;
    $("sysInfo").textContent = d ? `${demo ? "DEMO · " : ""}${d.brain_mode ? t("Modus {m}", { m: d.brain_mode }) + " · " : ""}LLM ${d.brain ? "✓" : "✗"} · Hermes ${d.hermes ? "✓" : "✗"} · STT ${d.stt ? "✓" : "✗"} · TTS ${d.tts ? "✓" : "…"}` : t("keine Verbindung");
    if (!S.busy && S.state !== "listening" && (changed || !d || S.state === "offline" || S.state === "idle")) restingState();
    if (changed && S.brain === true && S._wasOffline) { toast(t("Gehirn wieder online.")); earcon("up"); }
    S._wasOffline = S.brain === false;
    if (d) wakeApply(d.wake_word === true || qp.get("wake") === "1"); // ?wake=1 nur fuer Tests mit mock-wake.py
    if (d) { S.features = d.features || {}; setRooms(d.rooms); renderWake();
      // Name serverseitig geaendert (Admin, LLM-Werkzeug name_setzen im Image)? Uebernehmen, ausser ?name= ist gesetzt.
      if (window.I18N && d.assistant_name && d.assistant_name !== I18N.name && !qp.get("name") && !qp.get("brand")) { I18N.setName(d.assistant_name); I18N.reapply(); }
      if (document.activeElement !== $("optName")) $("optName").value = window.I18N ? I18N.name : (d.assistant_name || "");
      if ((d.onboarding === true || d.onboarded === false) && d.brain_ok && !ONB.started && !S.busy && !S.demo && S.state !== "listening") setTimeout(() => { if (!ONB.started && !S.busy) greet(false); }, 1500); }
    if (d) {
      opts.follow = d.follow_up !== false;
      opts.followTimeout = Math.max(4, Math.min(30, +d.follow_up_timeout_s || 8));
      $("optFollow").checked = opts.follow;
      if (!opts.follow && CONV.active) convEnd("ausgeschaltet");
    }
  }

  // ------------------------------------------------------------------ Audio: Kontext, Earcons, Wiedergabe
  let AC = null, outGain = null, outAnalyser = null;
  function audio() {
    if (!AC) {
      AC = new (window.AudioContext || window.webkitAudioContext)();
      outGain = AC.createGain(); outAnalyser = AC.createAnalyser(); outAnalyser.fftSize = 512;
      outGain.connect(outAnalyser); outAnalyser.connect(AC.destination);
    }
    if (AC.state === "suspended") AC.resume();
    return AC;
  }
  function earcon(kind) {
    if (!opts.earcons) return;
    try {
      const ac = audio(), t = ac.currentTime, o = ac.createOscillator(), g = ac.createGain();
      const f = { start: [660, 990], stop: [880, 520], up: [520, 1040], err: [300, 220], confirm: [740, 740] }[kind] || [600, 600];
      o.type = "sine"; o.frequency.setValueAtTime(f[0], t); o.frequency.exponentialRampToValueAtTime(f[1], t + .09);
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(.06, t + .012); g.gain.exponentialRampToValueAtTime(.0001, t + .16);
      o.connect(g); g.connect(ac.destination); o.start(t); o.stop(t + .18);
    } catch (e) { /* egal */ }
  }

  // satzweise TTS-Warteschlange mit Vorabladen.
  // Wiedergabe ueber EIN wiederverwendetes <audio>-Element (nicht WebAudio): WebKitGTK setzt den
  // AudioContext nach Mikrofon-Aufnahmen/ohne frische Geste auf "interrupted" -> stumm. Ein einmal per
  // Nutzergeste entsperrtes Media-Element spielt dagegen weiter. Der Orb-Pegel kommt aus den WAV-Samples.
  const player = new Audio(); player.preload = "auto"; player.setAttribute("playsinline", "");
  const SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
  let unlocked = false;
  function unlockAudio() {
    if (unlocked) return; unlocked = true;
    try { player.src = SILENT; const p = player.play(); if (p && p.catch) p.catch((e) => { unlocked = false; clog("Audio-Entsperren: " + e.name); }); } catch (e) { unlocked = false; }
    audio(); // Earcons + Fallback
  }
  document.addEventListener("pointerdown", unlockAudio, true);
  document.addEventListener("keydown", unlockAudio, true);

  // RMS-Huellkurve (50 ms) aus einer 16-bit-PCM-WAV fuer den Orb
  function wavEnvelope(ab) {
    try {
      const dv = new DataView(ab); let off = 12, rate = 22050, ch = 1, bits = 16, dataOff = -1, dataLen = 0;
      while (off + 8 <= dv.byteLength) {
        const id = String.fromCharCode(dv.getUint8(off), dv.getUint8(off + 1), dv.getUint8(off + 2), dv.getUint8(off + 3));
        const len = dv.getUint32(off + 4, true);
        if (id === "fmt ") { ch = dv.getUint16(off + 10, true); rate = dv.getUint32(off + 12, true); bits = dv.getUint16(off + 22, true); }
        if (id === "data") { dataOff = off + 8; dataLen = Math.min(len, dv.byteLength - dataOff); break; }
        off += 8 + len + (len & 1);
      }
      if (dataOff < 0 || bits !== 16) return { env: [], dur: 0 };
      const n = Math.floor(dataLen / 2 / ch), win = Math.max(1, Math.floor(rate * 0.05)), env = [];
      for (let i = 0; i < n; i += win) {
        let sum = 0; const e = Math.min(n, i + win);
        for (let k = i; k < e; k++) { const v = dv.getInt16(dataOff + k * 2 * ch, true) / 32768; sum += v * v; }
        env.push(Math.sqrt(sum / (e - i)));
      }
      return { env, dur: n / rate };
    } catch (e) { return { env: [], dur: 0 }; }
  }

  const speech = {
    queue: [], playing: null, gen: 0,
    say(text) {
      text = text.trim(); if (!text) return;
      this.lastText = text;
      if (!opts.voice) { clog("say übersprungen: Sprachausgabe aus"); return; }
      const item = { text, url: null, gen: this.gen };
      item.p = this.fetch(item); this.queue.push(item); this.pump();
    },
    async fetch(item) {
      try {
        const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: item.text }) });
        if (r.status !== 200) { clog("TTS HTTP " + r.status); return null; }
        const ab = await r.arrayBuffer();
        Object.assign(item, wavEnvelope(ab));
        item.url = URL.createObjectURL(new Blob([ab], { type: "audio/wav" }));
      } catch (e) { item.url = null; clog("TTS-Fehler: " + (e && (e.message || e.name || e))); }
      return item.url;
    },
    async pump() {
      if (this.playing || !this.queue.length) { this.idleCheck(); return; }
      const item = this.queue[0];
      this.playing = item;
      await item.p;
      if (item.gen !== this.gen) { if (item.url) URL.revokeObjectURL(item.url); return; }
      this.queue.shift();
      if (!item.url) { this.playing = null; this.pump(); return; }
      if (S.state !== "listening") setState("speaking", "");
      const next = () => { if (this.playing === item) { URL.revokeObjectURL(item.url); this.playing = null; this.pump(); } };
      player.onended = next;
      player.onerror = () => { clog("Wiedergabefehler " + (player.error && player.error.code)); next(); };
      player.src = item.url;
      try {
        await player.play();
        if (!this.loggedOk) { this.loggedOk = true; clog(`Wiedergabe läuft (<audio>), ${item.dur.toFixed(1)} s`); }
      } catch (e) {
        clog("play() abgelehnt: " + e.name + " – Fallback WebAudio");
        try {
          const ac = audio(); if (ac.state !== "running") await ac.resume().catch(() => {});
          const buf = await new Promise((res, rej) => { fetch(item.url).then((x) => x.arrayBuffer()).then((ab) => { const p = ac.decodeAudioData(ab, res, rej); if (p && p.then) p.then(res, rej); }, rej); });
          const src = ac.createBufferSource(); src.buffer = buf; src.connect(outGain); src.onended = next; item.src = src; src.start();
          clog("WebAudio-Fallback, Kontext " + ac.state);
        } catch (e2) { clog("Fallback fehlgeschlagen: " + (e2.message || e2)); next(); }
      }
    },
    level() {
      const it = this.playing; if (!it || !it.env || !it.env.length) return 0;
      const t = it.src ? 0 : player.currentTime; const v = it.env[Math.min(it.env.length - 1, Math.floor(t / 0.05))] || 0;
      return Math.min(1, v * 4);
    },
    idleCheck() {
      if (!this.playing && !this.queue.length) { this.endedAt = Date.now(); convCheck(); }
      // Auch ohne Audio (TTS 204/500, Piper aus) nicht in „Denke nach“ haengen bleiben: Lauf fertig -> Ruhe.
      if (!this.playing && !this.queue.length && S.state === "thinking" && !S.busy && !S.run && !S.approval) { restingState(); return; }
      if (!this.playing && !this.queue.length && S.state === "speaking") {
        if (S.approval) setState("thinking", t("wartet auf Freigabe"));
        else if (!S.busy) restingState(); else setState("thinking", S.thinkSub || "");
      }
    },
    stop() {
      this.gen++;
      for (const it of this.queue) { it.gen = -1; }
      this.queue = [];
      try { player.pause(); } catch (e) { /* egal */ }
      if (this.playing && this.playing.src) { try { this.playing.src.stop(); } catch (e) { /* egal */ } }
      this.playing = null;
    },
    get active() { return !!this.playing || this.queue.length > 0; },
  };

  // Pegel fuer Orb + PTT-Ring
  const lvlBuf = new Uint8Array(512);
  function rms(an) {
    an.getByteTimeDomainData(lvlBuf); let s = 0;
    for (let i = 0; i < lvlBuf.length; i++) { const v = (lvlBuf[i] - 128) / 128; s += v * v; }
    return Math.sqrt(s / lvlBuf.length);
  }
  function levelLoop() {
    requestAnimationFrame(levelLoop);
    if (S.state === "listening" && !rec.analyser && rec.mr) {
      const l = .25 + .1 * Math.sin(performance.now() / 300); Orb.set({ level: l });
      els.pttLevel.style.strokeDashoffset = String(352 - 352 * l);
    } else if (S.state === "listening" && rec.analyser) {
      const l = Math.min(1, rms(rec.analyser) * 4.5);
      Orb.set({ level: l });
      els.pttLevel.style.strokeDashoffset = String(352 - 352 * Math.min(1, .08 + l));
    } else if (S.state === "speaking") {
      const l = speech.playing && speech.playing.src && outAnalyser ? Math.min(1, rms(outAnalyser) * 3.2) : speech.level();
      Orb.set({ level: l });
    }
  }

  // ------------------------------------------------------------------ Aufnahme (Push-to-Talk)
  const rec = { stream: null, mr: null, chunks: [], analyser: null, t0: 0, timer: null, starting: false };
  const MIME = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm", "audio/mp4"].find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";

  async function startRec() {
    if (rec.mr || rec.starting) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) { toast(t("Mikrofon braucht HTTPS und einen aktuellen Browser.")); return; }
    rec.starting = true;
    interrupt();
    try {
      rec.stream = await navigator.mediaDevices.getUserMedia({ audio: opts.echoOff ? { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } : { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    } catch (e) {
      rec.starting = false; setState("error", t("Kein Mikrofonzugriff.")); earcon("err"); clog("Mikrofon verweigert: " + e.name + " " + e.message); return;
    }
    rec.starting = false;
    if (!S._micLogged) { S._micLogged = true; const tr = rec.stream.getAudioTracks()[0]; clog("Mikrofon offen: " + (tr && tr.label || "?") + " " + JSON.stringify(tr && tr.getSettings ? tr.getSettings() : {})); }
    if (rec.cancelled) { rec.cancelled = false; stopTracks(); return; }
    audio(); // Ausgabe-Kontext entsperren (Nutzergeste) – das Mikrofon kommt dort NICHT hinein
    // Pegel in einem eigenen, nicht hoerbaren Kontext: Quelle -> Analyser, nichts an destination.
    // Wird beim Stopp geschlossen. Abschaltbar mit ?micviz=0 bzw. Einstellung (Fehlersuche Rueckkopplung).
    // Derselbe Analyser speist die Sprachpausen-Erkennung (VAD) im Freihand-Modus.
    try {
      rec.ac = new (window.AudioContext || window.webkitAudioContext)();
      if (rec.ac.state !== "running") rec.ac.resume().catch(() => {});
      const srcNode = rec.ac.createMediaStreamSource(rec.stream);
      rec.vadAn = rec.ac.createAnalyser(); rec.vadAn.fftSize = 512; srcNode.connect(rec.vadAn);
      rec.analyser = opts.micviz ? rec.vadAn : null;
    } catch (e) { rec.analyser = rec.vadAn = null; clog("VAD nicht verfuegbar: " + (e.message || e)); }
    rec.chunks = [];
    rec.mr = new MediaRecorder(rec.stream, MIME ? { mimeType: MIME, audioBitsPerSecond: 32000 } : undefined);
    rec.mr.ondataavailable = (e) => { if (e.data && e.data.size) rec.chunks.push(e.data); };
    rec.mr.onstop = onRecStop;
    rec.mr.start(250);
    rec.t0 = Date.now();
    app.dataset.mic = "on";
    view("talk"); S.lastActivity = Date.now();
    setState("listening", "");
    earcon("start");
    if (navigator.vibrate) navigator.vibrate(12);
    rec.timer = setTimeout(() => stopRec(), 30000);
    vadStart();
    if (rec.pendingStop) { rec.pendingStop = false; stopRec(); }
  }
  // Sprachpausen-Erkennung (nur Freihand: Tippen, F14, „Hey NuOrb“): Ende nach VAD.SIL ms Stille, sobald gesprochen wurde;
  // ohne Sprache nach VAD.NONE ms Abbruch. Schwelle relativ zum gemessenen Grundrauschen. Halten = wie bisher bis Loslassen.
  const VAD = { FRAME: 50, SIL: 1000, NONE: 7000, MIN_SPEECH: 3, CAL: 250 };
  function vadStart() {
    vadStop(); rec.silent = false;
    if (!rec.vadAn) return;
    const v = rec.vad = { floor: 0, speech: 0, started: false, lastVoice: 0, t0: Date.now(), peak: 0 };
    rec.vadTimer = setInterval(() => {
      if (!rec.mr || !rec.vadAn) return;
      const r = rms(rec.vadAn), now = Date.now(), age = now - v.t0;
      if (age < VAD.CAL) { v.floor = v.floor ? Math.min(v.floor, r) : r; return; } // Start-Ton/Anlauf ueberspringen
      // Schwellen nach Messung am Handy (leises Mikro: Ruhe ~0,004, Sprache aus dem Lautsprecher bis ~0,02)
      const on = r > Math.max(0.010, v.floor * 3), off = r < Math.max(0.007, v.floor * 2);
      if (!on) v.floor = Math.min(0.05, Math.max(0.002, v.floor * 0.95 + r * 0.05)); // Grundrauschen nur in Pausen nachfuehren
      v.peak = Math.max(v.peak, r);
      // Sprachbeginn: Frames ueber der Schwelle zaehlen auf, Pausen bauen langsam ab (Silben sind kurz)
      if (on) { v.speech++; v.lastVoice = now; if (v.speech >= VAD.MIN_SPEECH && !v.started) v.started = true; } else if (off) v.speech = Math.max(0, v.speech - 0.25);
      if (!v.lastVoice) v.lastVoice = v.t0;
      if (app.dataset.latched !== "true") return; // Halten: kein automatisches Ende
      if (v.blind || (age > 1500 && v.peak < 0.0005)) { if (!v.blind) { v.blind = true; clog("VAD blind (Analyser liefert nur Stille) – Ende per Tippen oder nach 30 s"); } return; }
      if (v.started && now - v.lastVoice > VAD.SIL) { clog(`VAD: Ende nach ${(age / 1000).toFixed(1)} s (Rauschen ${v.floor.toFixed(3)}, Spitze ${v.peak.toFixed(3)})`); stopRec(); }
      else if (!v.started && age > (rec.noneMs || VAD.NONE)) {
        // Nur wirklich stille Aufnahmen verwerfen; gab es Ausschlaege, entscheidet die Spracherkennung.
        // Im Gespraechsmodus (Nachfrage) nur sicher erkannte Sprache – sonst landen Nachhall/Raum als Frage bei Hermes.
        const loud = !rec.conv && v.peak > Math.max(0.010, v.floor * 3);
        clog(`VAD: ${loud ? "unsicher, sende" : "keine Sprache"} (Rauschen ${v.floor.toFixed(3)}, Spitze ${v.peak.toFixed(3)})`);
        if (loud) stopRec(); else { rec.silent = true; stopRec(true); }
      }
    }, VAD.FRAME);
  }
  function vadStop() { if (rec.vadTimer) { clearInterval(rec.vadTimer); rec.vadTimer = null; } }
  // Freihand-Aufnahme starten (Tippen-Ersatz fuer F14 und das Wake-Word)
  function handsFree(source, o) {
    if (S.state === "listening") return;
    audio(); unlockAudio(); S.lastActivity = Date.now();
    if (S.busy || speech.active) interrupt(true);
    rec.noneMs = o && o.noneMs || 0; rec.conv = !!(o && o.conv);
    app.dataset.latched = "true"; startRec(); if (source) clog("Freihand: " + source);
  }
  function stopTracks() {
    if (rec.stream) rec.stream.getTracks().forEach((t) => t.stop());
    vadStop();
    rec.stream = null; rec.analyser = rec.vadAn = null; app.dataset.mic = "off";
    if (rec.ac) { try { rec.ac.close(); } catch (e) { /* egal */ } rec.ac = null; }
  }
  function stopRec(cancel) {
    if (rec.starting) { if (cancel) rec.cancelled = true; else rec.pendingStop = true; return; }
    if (!rec.mr) return;
    clearTimeout(rec.timer);
    rec.cancel = !!cancel; rec.wasLatched = app.dataset.latched === "true";
    try { rec.mr.stop(); } catch (e) { onRecStop(); }
    app.dataset.latched = "false";
  }
  async function onRecStop() {
    const dur = Date.now() - rec.t0, chunks = rec.chunks, type = (rec.mr && rec.mr.mimeType) || MIME || "audio/webm";
    rec.mr = null; stopTracks(); els.pttLevel.style.strokeDashoffset = "352";
    earcon("stop");
    const wasConv = rec.conv, latched = rec.wasLatched || rec.noneMs > 0; rec.conv = false; rec.noneMs = 0;
    if (rec.cancel || dur < 350 || !chunks.length) {
      if (wasConv && rec.silent) { convEnd("Stille"); return; } // Nachfrage ohne Antwort: leise zurueck in Bereitschaft
      restingState(); if (rec.silent) toast(t("Ich habe nichts gehört.")); return;
    }
    const blob = new Blob(chunks, { type });
    setState("transcribing", "");
    S.busy = true; app.dataset.busy = "true";
    try {
      const fd = new FormData(); fd.append("audio", blob, "aufnahme." + (type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm"));
      const r = await fetch("/api/stt", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || t("Spracherkennung fehlgeschlagen"));
      const d = await r.json();
      S.busy = false;
      if (!d.text) { if (wasConv) { convEnd("nichts verstanden"); return; } restingState(); toast(t("Ich habe nichts verstanden.")); return; }
      if (CONV.active && (DE ? CONV_END : CONV_END_EN).test(normSay(d.text))) { card("user", d.text); convEnd("Nutzer", true); return; }
      convTouch(latched || wasConv);
      if (localCommand(d.text)) return;
      if (S.brain === false) { card("user", d.text); offlineReply(); return; }
      ask(d.text);
    } catch (e) {
      S.busy = false; setState("error", String(e.message || e)); earcon("err");
      setTimeout(() => { if (S.state === "error") restingState(); }, 4000);
    }
  }

  // Taste: halten = Push-to-Talk; kurzes Tippen = Freihand (nochmal tippen zum Senden); waehrend Antwort = unterbrechen
  let downAt = 0, downState = "";
  els.ptt.addEventListener("pointerdown", (e) => {
    e.preventDefault(); els.ptt.setPointerCapture(e.pointerId);
    audio(); downAt = Date.now(); downState = S.state;
    if (S.state === "listening") { stopRec(); return; }       // Freihand beenden
    if (S.busy || speech.active) { interrupt(true); restingState(); downState = "interrupted"; if (CONV.active) setTimeout(() => handsFree("Gespräch (unterbrochen)", { conv: true, noneMs: opts.followTimeout * 1000 }), 350); return; }
    startRec();
  });
  // Tippen vs. Halten: alles unter TAP_MS gilt als Tippen (Freihand mit Pausen-Erkennung). Finger-Tipps auf dem Handy
  // dauern oft 300-500 ms, und der erste getUserMedia-Aufruf nach dem Laden braucht spuerbar – daher grosszuegig.
  const TAP_MS = 700;
  const release = (e) => {
    const held = Date.now() - downAt, was = downState; downState = "";
    if (!was) return; // schon behandelt (pointerup nach pointercancel o. ae.)
    clog(`PTT los: ${held} ms, vorher ${was}, ${e ? e.type : "-"}, Aufnahme ${rec.mr ? "laeuft" : rec.starting ? "startet" : "aus"}`);
    if (was === "listening" || was === "interrupted") return;
    if (!rec.mr && !rec.starting) return; // nichts aufgenommen (z. B. Mikrofon verweigert)
    if (held < TAP_MS || (e && e.type === "pointercancel" && held < 3000)) { app.dataset.latched = "true"; setState("listening", ""); return; }
    stopRec(false);
  };
  els.ptt.addEventListener("pointerup", release);
  els.ptt.addEventListener("pointercancel", release);
  els.ptt.addEventListener("contextmenu", (e) => e.preventDefault());

  // ------------------------------------------------------------------ Gespraechsmodus
  // Nach einer Antwort auf eine gesprochene Frage (Tippen, Halten, F14, „Hey NuOrb“) fragt NuOrb kurz nach und hoert
  // ohne Wake-Word wieder zu (opts.followTimeout s bis zum Sprachbeginn). Ende: Abschiedssatz, Stille, 20 Runden, 5 min.
  // Nie waehrend offener Karte (Karten bleiben Tippen-only), nie waehrend Sprachausgabe (kein Echo ins Mikro).
  const CONV_ASK = [t("Noch etwas?"), t("Kann ich noch etwas für dich tun?"), t("Sonst noch was?"), t("Noch eine Frage?")];
  const CONV_END = /^(nein|nee|ne|nö|nichts|nix|danke|das war'?s|das wars|das ist alles|passt|ruhemodus|ruhe|schlaf\w*|gute nacht|tschüss|tschau|bis später|bis dann|stopp?|ende|fertig|ok(ay)? danke)( (danke|das war'?s|das wars|mehr|nuorb|schön|sehr|alles|gut|bitte|für jetzt))*$/;
  const CONV_END_EN = /^(no|nope|nothing|no thanks?|no thank you|thanks?|thank you|that'?s all|that'?s it|thats all|thats it|goodbye|good ?bye|bye|good night|stop|sleep|nothing else|all good)( (thanks?|thank you|nuorb|for now|that'?s all|thats all|bye|then))*$/;
  const normSay = (t) => String(t).toLowerCase().replace(/[.!?,;:]/g, " ").replace(/\s+/g, " ").trim();
  function convTouch(start) {
    if (!opts.follow) { CONV.active = false; return; }
    if (!CONV.active && !start) return;
    if (!CONV.active) { CONV.active = true; CONV.rounds = 0; clog("Gespräch beginnt"); }
    CONV.rounds++; CONV.lastAt = Date.now(); CONV.prompted = false;
  }
  function convEnd(why, say) {
    if (!CONV.active) return;
    CONV.active = false; clearTimeout(CONV.timer); clog(`Gespräch endet (${why}, ${CONV.rounds} Runden)`);
    if (say) speech.say(t("Okay, ich bin da, wenn du mich brauchst."));
    if (!S.busy && !speech.active) restingState();
    if (WAKE.on) { els.stateSub.textContent = t("Sag „Hey NuOrb“"); }
  }
  function convCheck() {
    clearTimeout(CONV.timer);
    if (!CONV.active) return;
    CONV.timer = setTimeout(() => {
      if (!CONV.active || S.busy || S.run || S.approval || rec.mr || rec.starting || speech.active || S.state === "listening" || S.state === "transcribing") return;
      if (CONV.rounds >= 20 || Date.now() - CONV.lastAt > 300000) return convEnd(CONV.rounds >= 20 ? "20 Runden" : "5 min");
      const last = String(speech.lastText || "").trim();
      if (!CONV.prompted && !/[?]["“”»]?$/.test(last)) {
        CONV.prompted = true; speech.say(CONV_ASK[CONV.n++ % CONV_ASK.length]); return; // nach der Nachfrage kommt convCheck erneut
      }
      CONV.prompted = true;
      handsFree("Gespräch", { conv: true, noneMs: opts.followTimeout * 1000 });
    }, 700); // Nachhall abwarten, bevor das Mikro aufgeht
  }

  function offlineReply() {
    const lines = [
      t("Mein Gehirn ist gerade offline. Sobald der PC läuft, bin ich wieder ganz für dich da."),
      t("Der PC schläft, und mit ihm mein Sprachmodell. Uhr und Notizen laufen trotzdem."),
    ];
    const line = lines[Math.floor(Math.random() * lines.length)];
    card("sys", t("Gehirn offline – Frage nicht möglich."));
    speech.say(line);
  }

  // ------------------------------------------------------------------ Hermes-Run
  function interrupt(stopRun) {
    speech.stop();
    if (stopRun && S.run) {
      fetch(`/api/runs/${encodeURIComponent(S.run)}/stop`, { method: "POST" }).catch(() => {});
      if (S.abort) S.abort.abort();
      card("sys", t("Unterbrochen."));
      S.run = null; S.busy = false;
    }
  }

  async function ask(text, retry, noCard) {
    if (!retry && !noCard) card("user", text);
    S.busy = true; setState("thinking", retry ? t("zweiter Versuch") : "");
    let res;
    try {
      const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, session_id: S.session, device: ANDROID ? "" : deviceSummary(), no_haiku: !!retry,
        ...(ANDROID ? { client: "android", wake: !!WAKE.on } : {}) }) });
      res = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(r.status === 503 && res.code === "no_brain" && res.detail ? String(res.detail) : r.status === 503 ? t("Hermes ist nicht erreichbar.") : r.status === 429 ? t("Hermes ist ausgelastet.") : (res.detail || t("Fehler {s}", { s: r.status })));
    } catch (e) { return fail(String(e.message || e)); }
    S.session = res.session_id; store.set("session", S.session); store.set("sessionDay", today);
    S.run = res.run_id;
    // Geraete-Weiche (Haiku): schlaegt der Lauf fehl, bevor etwas kam, denselben Satz einmal ans Standard-Gehirn
    S.retryAsk = res.route === "geraet" && !retry ? text : null;
    if (res.route === "geraet") clog("Geraete-Weiche: Haiku");
    streamRun(res.run_id);
  }

  function fail(msg) {
    if (CONV.active) convEnd("Fehler");
    S.busy = false; S.run = null; card("err", msg); earcon("err");
    setState("error", ""); speech.say(t("Da ist etwas schiefgelaufen.") + " " + (S.brain === false ? t("Mein Gehirn ist offline.") : ""));
    setTimeout(() => { if (S.state === "error") restingState(); }, 5000);
  }

  // Steuer-Reste aus Gemma/Ollama entfernen (siehe NOTES-backend §10)
  const JUNK = /<\|?\/?(?:channel|tool_call|tool_response)\|?>|<\|"\|>/gi;
  const MAX_ANSWER = 900; // Zeichen; laengere Sprachantworten werden gestoppt
  function cleanOut(t) {
    return String(t || "").replace(/(^|\n)[ \t]*\[\d{1,2}:\d{2}\][ \t]*/g, "$1").replace(/\n{3,}/g, "\n\n").replace(JUNK, "").replace(/(^|[\s.!?:])thought(?=[ \t]*(?:\n|$|<))/gi, "$1").replace(/^[\s|}]+/, "").trim();
  }
  const letters = (t) => (String(t).match(/[A-Za-zÄÖÜäöüß]/g) || []).length;
  // Englischer Denktext („The current brightness isn't …, so I'll use …“) gehoert nicht in die deutsche Antwort:
  // Saetze (auch den noch offenen letzten) mit >=3 englischen und <=1 deutschen Funktionswoertern verwerfen.
  const EN_W = /\b(the|is|isn't|it's|i'll|i'm|i|so|will|would|should|use|using|value|message|current|this|that|there|user|let|me|we|need|tool|call|default|moderate|which|because|then|now|just|isn|don't|can't|they|their)\b/gi;
  const DE_W = /\b(der|die|das|und|ist|nicht|ich|du|dich|dir|es|ein|eine|einen|auf|mit|zu|für|von|den|dem|im|wird|sind|gerade|prozent|grad|uhr|noch|schon|auch|bitte)\b|[äöüß]/gi;
  function stripEnglish(t) {
    if (!DE) return t; // englische Oberflaeche: Antworten sind englisch
    const parts = String(t).match(/[^.!?]+(?:[.!?]+|$)\s*/g) || [];
    const keep = parts.filter((p) => !((p.match(EN_W) || []).length >= 3 && (p.match(DE_W) || []).length <= 1));
    return keep.length === parts.length ? t : keep.join("").trim();
  }
  async function streamRun(runId) {
    const ctl = new AbortController(); S.abort = ctl;
    let aiCard = null, full = "", spoken = 0, gotDelta = false, finished = false, failed = false;
    const seen = {}; let claudeSaid = false; const doneActions = new Set(); let devRequested = false;
    let raw = "", preTool = "", toolSeen = false, capped = false; S.lastIntentSay = null;
    const tools = {};
    const ensureCard = () => { if (!aiCard) { aiCard = card("ai", ""); aiCard.classList.add("streaming"); } return aiCard; };

    // Satzgrenzen erkennen; „24. November“ oder „z. B.“ nicht trennen
    const flush = (final) => {
      let rest = full.slice(spoken);
      for (;;) {
        const m = /([.!?…;:])(\s+|$)|\n+/g; let cut = -1, x;
        while ((x = m.exec(rest))) {
          const end = x.index + x[0].length, before = rest.slice(0, x.index);
          if (x[0].startsWith("\n") || (x[2] === "" && !final)) { if (x[0].startsWith("\n") && before.trim().length) { cut = end; break; } continue; }
          if (/\d$/.test(before) && x[1] === ".") continue;
          if (/\b(z|d|u|bzw|ca|Nr|Dr|St|usw|vgl|ggf|inkl|etc)$/i.test(before) || /\b\w$/.test(before)) continue;
          if (before.trim().length >= 18 || final) { cut = end; break; }
        }
        if (cut < 0) break;
        speech.say(rest.slice(0, cut)); spoken += cut; rest = full.slice(spoken);
      }
      if (final && rest.trim()) { speech.say(rest); spoken = full.length; }
    };

    // Waechter: kommt 2 min lang gar nichts (z. B. PC-GPU belegt, Gemma haengt), Lauf stoppen und ehrlich melden.
    // Laeuft ein Werkzeug (Projekt-Claude bis 10 min) oder wartet eine Karte, gilt 11 min bzw. kein Limit.
    let lastEv = Date.now(), openTools = 0;
    const watch = setInterval(() => {
      if (finished || ctl.signal.aborted) return clearInterval(watch);
      if (S.approval) { lastEv = Date.now(); return; }
      if (Date.now() - lastEv > (openTools > 0 ? 660000 : 120000)) {
        clearInterval(watch); clog(`Run ${runId.slice(0, 12)}: keine Ereignisse seit ${Math.round((Date.now() - lastEv) / 1000)} s – abgebrochen`);
        fetch(`/api/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" }).catch(() => {});
        finished = true; ctl.abort(); speech.stop(); S.retryAsk = null;
        fail(S.brain === false ? t("Gehirn offline.") : t("Das Sprachmodell antwortet gerade nicht (2 Minuten ohne Lebenszeichen). Abgebrochen – bitte gleich nochmal versuchen."));
      }
    }, 5000);
    const handle = (ev) => {
      S.lastActivity = Date.now(); lastEv = Date.now(); seen[ev.event] = (seen[ev.event] || 0) + 1;
      if (ev.event === "tool.started") openTools++; else if (ev.event === "tool.completed") openTools = Math.max(0, openTools - 1);
      switch (ev.event) {
        case "message.delta": {
          if (!ev.delta || capped) break;
          gotDelta = true; raw += ev.delta;
          if (!toolSeen) preTool = raw; // Vortext des Werkzeug-Turns (falls die Endantwort kaputt ist)
          let c = stripEnglish(cleanOut(raw));
          // Modell wiederholt manchmal den Zeitstempel „[12:30]“ aus der Nutzernachricht – weg damit
          if (/^\[[^\]]*$/.test(c) && c.length < 260) break;
          c = c.replace(/^\[[^\]]{0,260}\]\s*/, "");
          if (letters(c) < 8 && !/[.!?]/.test(c)) break; // evtl. noch Steuer-Rest („thought“) – abwarten
          full = c; spoken = Math.min(spoken, full.length);
          ensureCard().textContent = full; els.convo.scrollTop = els.convo.scrollHeight;
          if (full.length > MAX_ANSWER) { // Ersatz fuer max_tokens (bei /v1/runs nicht pro Anfrage einstellbar)
            capped = true; clog("Antwort gekappt bei " + full.length + " Zeichen");
            fetch(`/api/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" }).catch(() => {});
            full = full.slice(0, MAX_ANSWER).replace(/[^.!?]*$/, "") || full.slice(0, MAX_ANSWER);
            ensureCard().textContent = full + " …"; flush(true); break;
          }
          flush(false); break;
        }
        case "tool.started": {
          toolSeen = true;
          if (ANDROID && /geraet_+anfordern$/.test(ev.tool || "") && !capped) {
            // Android-App: keine Geraetesteuerung. Vortext/Behauptungen des Modells verwerfen, festen Satz sprechen.
            capped = true; speech.stop(); full = t("Gerätebefehle gehen in dieser App nicht."); spoken = 0;
            ensureCard().textContent = full; flush(true); clog("Android: Geraete-Werkzeug abgefangen");
            break;
          }
          const chip = toolChip(ev.tool, (ev.preview || "").slice(0, 80));
          tools[ev.tool_call_id || ev.tool] = chip;
          if (/^mcp_claude_/.test(ev.tool || "")) {
            S.thinkSub = t("Claude arbeitet …"); setState("thinking", S.thinkSub);
            if (!claudeSaid && !/aenderungen/.test(ev.tool)) { claudeSaid = true; speech.say(t("Einen Moment, Claude arbeitet daran.")); }
          } else if (!speech.active) setState("thinking", TOOLNAME(ev.tool) + " …");
          break;
        }
        case "tool.completed": {
          const chip = tools[ev.tool_call_id || ev.tool];
          if (chip) chip.classList.add(ev.error ? "fail" : "done");
          S.thinkSub = "";
          // Absichts-Werkzeug von sprachsteuerung: Hermes fordert nur an, ausgefuehrt wird lokal (mit eigener Karte)
          // Name im SSE: mcp__geraet__anfordern. preview ist leer (Hermes) -> Ergebnis ueber den Server aus dem Verlauf holen.
          if (/geraet_+anfordern$/.test(ev.tool || "") && !ev.error) {
            const m = String(ev.preview || "").match(/GERAET_AKTION\s*(\{[^{}]*\})/);
            const key = ev.tool_call_id || ev.preview;
            if (!doneActions.has(key)) {
              doneActions.add(key); devRequested = true;
              if (m) { try { deviceIntent(JSON.parse(m[1])); } catch (e) { clog("GERAET_AKTION unlesbar: " + m[1]); } }
              else if (ev.tool_call_id) fetchIntent(S.session, ev.tool_call_id);
            }
          }
          break;
        }
        case "reasoning.available":
          if (!speech.active && S.state === "thinking") els.stateSub.textContent = t("überlege …"); break;
        case "approval.request": showApproval(runId, ev); break;
        case "approval.responded": hideRunApproval(); break;
        case "run.queued": els.stateSub.textContent = t("in der Warteschlange …"); break;
        case "run.completed": {
          finished = true;
          if (capped) break;
          const out = cleanOut(typeof ev.output === "string" ? ev.output : "").replace(/^\[[^\]]{0,260}\]\s*/, "");
          if (!gotDelta && out) full = out;
          else if (out && out.length > full.length && out.startsWith(full)) full = out;
          full = stripEnglish(cleanOut(full));
          // Gemma (Ollama-Renderer) liefert nach Werkzeugaufrufen teils nur Reste: „thought“, „<channel|>“, „}“, JSON …
          if (letters(full) < 8 || /^\s*[{\[]/.test(full)) {
            const pre = cleanOut(preTool).replace(/^\[[^\]]{0,260}\]\s*/, "");
            clog("Kaputte Endausgabe ersetzt: " + JSON.stringify(String(ev.output || "").slice(0, 40)));
            full = letters(pre) >= 8 ? pre : (devRequested ? (S.lastIntentSay || t("Erledige ich.")) : t("Dazu habe ich gerade keine Antwort."));
          }
          spoken = Math.min(spoken, full.length); ensureCard().textContent = full;
          flush(true); break;
        }
        case "run.failed": case "run.cancelled": case "run.interrupted":
          finished = true; failed = true;
          if (aiCard) aiCard.classList.remove("streaming");
          if (ev.event === "run.failed" && S.retryAsk && !gotDelta && !toolSeen) {
            const t = S.retryAsk; S.retryAsk = null; S.run = null;
            clog("Haiku-Lauf fehlgeschlagen (" + String(ev.error || "").slice(0, 80) + ") – nochmal mit Standard-Gehirn");
            return ask(t, true);
          }
          if (ev.event === "run.failed") {
            const offline = S.brain === false;
            S.busy = false; S.run = null; hideRunApproval();
            const er = String(ev.error || "");
            const why = offline ? t("Gehirn offline – das Sprachmodell auf dem PC ist nicht erreichbar.")
              : /too large|context|token/i.test(er) ? t("Das Sprachmodell hat zu wenig Kontext für Hermes (Backend-Einstellung nötig).")
              : /connect|refused|unreachable|timed? ?out/i.test(er) ? t("Das Sprachmodell antwortet nicht. Läuft Ollama auf dem PC?")
              : t("Hermes: {e}", { e: er || t("Lauf fehlgeschlagen") });
            return fail(why);
          }
          card("sys", ev.event === "run.cancelled" ? t("Abgebrochen.") : t("Unterbrochen."));
          break;
      }
    };

    try {
      const r = await fetch(`/api/runs/${encodeURIComponent(runId)}/events`, { signal: ctl.signal, headers: { Accept: "text/event-stream" } });
      const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, i); buf = buf.slice(i + 2);
          for (const line of block.split("\n")) {
            if (!line.startsWith("data:")) continue;
            try { handle(JSON.parse(line.slice(5).trim())); } catch (e) { /* unvollstaendig */ }
          }
          if (finished) break;
        }
        if (finished) { try { reader.cancel(); } catch (e) { /* egal */ } break; }
      }
    } catch (e) {
      if (ctl.signal.aborted) return;
      // Stream abgerissen: Status einmal pollen
      try { const st = await (await fetch(`/api/runs/${encodeURIComponent(runId)}`)).json(); if (st.output) handle({ event: "run.completed", output: st.output }); finished = !!st.output; } catch (e2) { /* egal */ }
      if (!finished) return fail(t("Verbindung zum Lauf verloren."));
    }
    setTimeout(convCheck, 50); // auch ohne Sprachausgabe (Stimme aus) weiter im Gespraech
    clog(`Run ${runId.slice(0, 12)}: Ereignisse ${JSON.stringify(seen)}, fertig=${finished}, Text ${full.length} Z., gesprochen ${spoken}`);
    if (!finished && S.run === runId) {
      // Stream endete ohne Abschluss-Ereignis: Status nachladen und Antwort trotzdem aussprechen
      try { const st = await (await fetch(`/api/runs/${encodeURIComponent(runId)}`)).json();
        if (st.output) handle({ event: "run.completed", output: st.output }); } catch (e) { /* egal */ }
    }
    if (full.trim() && spoken < full.length && !failed) flush(true);
    if (aiCard) aiCard.classList.remove("streaming");
    if (S.run === runId) { S.run = null; S.busy = false; }
    S.thinkSub = "";
    hideRunApproval();
    if (!speech.active) restingState();
  }

  // ------------------------------------------------------------------ Bestaetigungskarten
  // Feste deutsche Karten fuer bekannte MCP-Werkzeuge (Server „claude“ = Projekt-Claude, Sitzung sprachsteuerung).
  // Kosten und Argumente stehen im command-Text: „Costs 1-30 Cent (…)“, „Arguments: {json}“.
  const CLAUDE_ZIEL = t("Projekt-Claude (Sonnet 5.5), Ordner nuorb-ui (Arbeitskopie auf nuorb)");
  const KNOWN = {
    "claude:fragen": { title: t("Claude fragen?"), ziel: CLAUDE_ZIEL, befehl: t("nur lesen und durchsuchen"), arg: ["frage", t("Frage")],
      kosten: t("ca. 1–30 Cent"), folgen: t("Claude antwortet auf Deutsch in höchstens fünf Sätzen. Es wird nichts geändert."),
      yes: t("Ja, fragen"), say: t("Soll ich Claude das fragen? Kostet ein paar Cent.") },
    "claude:auftrag": { title: t("Claude-Auftrag ausführen?"), ziel: CLAUDE_ZIEL, befehl: t("Dateien lesen und ändern, keine Befehle ausführen"), arg: ["auftrag", t("Auftrag")],
      kosten: t("ca. 5–100 Cent"), folgen: t("Die Änderung wird als Git-Commit gespeichert und lässt sich mit „rückgängig“ zurücknehmen. Die laufende Oberfläche bleibt unverändert."),
      yes: t("Ja, ausführen"), say: t("Soll Claude das wirklich ändern?") },
    "claude:rueckgaengig": { title: t("Letzte Claude-Änderung zurücknehmen?"), ziel: CLAUDE_ZIEL, befehl: t("git revert der letzten Claude-Änderung"),
      kosten: t("kostenlos"), folgen: t("Die letzte Änderung von Claude wird mit einem neuen Commit zurückgenommen."),
      yes: t("Ja, zurücknehmen"), say: t("Soll ich die letzte Änderung von Claude zurücknehmen?") },
  };
  // Haus-Schalter (Server zuhause_schalten, sprachsteuerung): Karte aus den Argumenten bauen
  const ZH_ZIEL = t("Haus-Dashboard (Heizung/Klima)");
  KNOWN["zuhause_schalten:klima_stellen"] = { ziel: ZH_ZIEL, kosten: t("kostenlos"), fmt: (a) => {
    const g = a.geraet === "alle" ? t("alle Klimaanlagen") : t("Klimaanlage {g}", { g: a.geraet || "?" });
    const aus = a.an === false, s = a.soll;
    return { title: aus ? t("{g} ausschalten?", { g }) : a.an ? t("{g} einschalten?", { g }) : t("{g} einstellen?", { g }),
      facts: [[t("Gerät"), g], aus ? null : [t("Modus"), a.modus], aus ? null : [t("Soll"), a.soll != null ? a.soll + " °C" : null], aus ? null : [t("Lüfter"), a.luefter]].filter(Boolean),
      say: aus ? t("Soll ich {g} ausschalten?", { g })
        : a.soll != null ? (a.an ? t("Soll ich {g} einschalten auf {s} Grad?", { g, s }) : t("Soll ich {g} einstellen auf {s} Grad?", { g, s }))
        : a.an ? t("Soll ich {g} einschalten?", { g }) : t("Soll ich {g} einstellen?", { g }),
      yes: aus ? t("Ja, ausschalten") : a.an ? t("Ja, einschalten") : t("Ja, einstellen"), folgen: t("Die Anlage wird über das Haus-Dashboard gestellt.") }; } };
  KNOWN["zuhause_schalten:raum_soll_gross"] = { ziel: ZH_ZIEL, kosten: t("kostenlos"), fmt: (a) => {
    const ziel = a.soll != null ? a.soll + " °C" : (a.aendern > 0 ? "+" : "") + a.aendern + " K";
    return { title: t("{r}: Soll-Temperatur auf {z}?", { r: a.raum || t("Raum"), z: ziel }), facts: [[t("Raum"), a.raum], [t("Neu"), ziel]],
      say: a.soll != null ? t("Soll ich {r} auf {s} Grad stellen?", { r: a.raum || t("den Raum"), s: a.soll }) : t("Soll ich {r} auf {z} stellen?", { r: a.raum || t("den Raum"), z: ziel }),
      yes: t("Ja, einstellen"),
      folgen: t("Größere Änderung (über drei Grad) – deshalb diese Rückfrage.") }; } };
  function mcpDetails(cmd) {
    const out = {};
    const c = cmd.match(/Costs?\s+([0-9]+(?:\s*[-–]\s*[0-9]+)?)\s*Cent/i);
    if (c) out.kosten = t("ca. {c} Cent", { c: c[1].replace(/\s*[-–]\s*/, "–") });
    const a = cmd.match(/Arguments:\s*(\{[\s\S]*\})/);
    if (a) { try { out.args = JSON.parse(a[1]); } catch (e) { /* redigiert/abgeschnitten */ } }
    return out;
  }
  function setFacts(rows) {
    const dl = $("apFacts"); dl.replaceChildren();
    for (const [k, v] of rows) { if (!v) continue; const dt = document.createElement("dt"); dt.textContent = k; const dd = document.createElement("dd"); dd.textContent = v; dl.append(dt, dd); }
    dl.hidden = !dl.children.length;
  }
  function showApproval(runId, ev) {
    S.approval = { runId, request_id: ev.request_id || ev.prompt_id || null, execution_generation: ev.execution_generation ?? null };
    const cmd = String(ev.command || ev.preview || "");
    const raw = String(ev.description || ev.reason || "").trim();
    const mcp = cmd.match(/MCP tool '([\w.-]+)' on (?:UNTRUSTED )?server '([\w.-]+)'/i) || raw.match(/run '([\w.-]+)'.*?Server '([\w.-]+)'/i);
    let title = t("NuOrb möchte etwas ausführen"), desc, facts = [], code = cmd, yes = t("Ja, ausführen"), say = t("Ich brauche deine Bestätigung.");
    if (mcp) {
      const [, tool, server] = mcp, k = KNOWN[server + ":" + tool];
      const det = mcpDetails(cmd);
      if (k && k.fmt && det.args) {
        const f = k.fmt(det.args); title = f.title; desc = f.folgen; yes = f.yes; say = f.say; code = "";
        facts = [[t("Ziel"), k.ziel], ...f.facts.map(([a, b]) => [a, b != null ? String(b) : null])];
      } else if (k && !k.fmt) {
        title = k.title; desc = k.folgen; yes = k.yes; say = k.say; code = "";
        const argVal = k.arg && det.args ? det.args[k.arg[0]] : null;
        facts = [[t("Ziel"), k.ziel], [t("Befehl"), k.befehl], k.arg ? [k.arg[1], argVal ? String(argVal) : t("(nicht lesbar)")] : null,
          [t("Kosten"), det.kosten || k.kosten]].filter(Boolean);
      }
      else {
        title = server === "handy" ? t("Smartphone-Werkzeug „{tool}“ ausführen?", { tool }) : t("Werkzeug „{tool}“ von „{server}“ ausführen?", { tool, server });
        desc = t("Der Server „{server}“ ist als nicht vertrauenswürdig eingestuft; jede schreibende Aktion braucht deine Freigabe.", { server });
        facts = [[t("Werkzeug"), server + " · " + tool], [t("Kosten"), det.kosten]];
        if (det.args) code = JSON.stringify(det.args, null, 1).slice(0, 600);
        say = t("Darf ich das Werkzeug {tool} ausführen?", { tool });
      }
    } else {
      const RISK = [[/recursive delete|rm -r/i, t("Rekursives Löschen – Dateien und Ordner werden endgültig entfernt.")],
        [/delete|remov/i, t("Löschen von Dateien.")], [/overwrit|truncat/i, t("Überschreiben von Dateien.")],
        [/sudo|privilege|root/i, t("Befehl mit erhöhten Rechten.")], [/chmod|chown|permission/i, t("Ändern von Rechten oder Besitzern.")],
        [/kill|shutdown|reboot|systemctl/i, t("Eingriff in laufende Dienste oder das System.")], [/network|curl|wget|download/i, t("Netzwerkzugriff / Download.")],
        [/git push|force/i, t("Erzwungene Änderung (z. B. force push).")], [/install|package/i, t("Installation von Paketen.")],
        [/write|edit|patch/i, t("Schreiben in Dateien.")], [/mcp|consent|untrusted/i, t("Werkzeug eines nicht vertrauenswürdigen Servers.")]];
      const hit = raw && RISK.find(([rx]) => rx.test(raw));
      desc = hit ? hit[1] : raw ? t("Hermes stuft das als gefährlich ein: {r}", { r: raw }) : t("Diese Aktion ist als gefährlich eingestuft und braucht deine Freigabe.");
      if (/rm -r/i.test(cmd)) say = t("Soll ich das wirklich löschen?");
    }
    $("apTitle").textContent = title;
    $("apDesc").textContent = desc;
    setFacts(facts);
    $("apCmd").textContent = code;
    $("apYes").textContent = yes;
    $("approvalBackdrop").hidden = false; setTimeout(() => $("apNo").focus(), 50);
    view("talk"); setState("thinking", t("wartet auf Freigabe"));
    earcon("confirm"); if (navigator.vibrate) navigator.vibrate([30, 60, 30]);
    speech.say(say);
    clog("Bestätigungskarte: " + title);
  }
  function hideApproval() { $("approvalBackdrop").hidden = true; S.approval = null; }
  // Run-Ende schliesst nur Hermes-Karten, nicht lokale (Geraet/Gehirn), die waehrend des Runs aufgegangen sind
  function hideRunApproval() { if (S.approval && S.approval.local) return; hideApproval(); }
  async function answerApproval(choice) {
    const a = S.approval; if (!a) return;
    if (a.local) {
      hideApproval(); try { await a.local(choice); } catch (e) { toast(String(e.message || e)); }
      if (!S.busy && !S.run && !rec.mr && !speech.active) restingState(); // lokale Karte: Zustand zuruecksetzen (sonst nach der Ansage)
      return;
    }
    $("apYes").disabled = $("apNo").disabled = true;
    try {
      const r = await fetch(`/api/runs/${encodeURIComponent(a.runId)}/approval`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choice, request_id: a.request_id, execution_generation: a.execution_generation }) });
      if (!r.ok) { const d = await r.json().catch(() => ({})); toast(t("Freigabe nicht angenommen: {e}", { e: d.error?.message || d.detail || r.status })); }
      else card("sys", choice === "once" ? t("Freigegeben.") : t("Abgelehnt."));
    } catch (e) { toast(t("Freigabe fehlgeschlagen.")); }
    $("apYes").disabled = $("apNo").disabled = false;
    hideApproval();
  }
  // Schutz: lokale Karten (Neustart/Ausschalten/WLAN/Gehirn) nur per echtem Tippen/Klicken auf „Ja“ bestaetigen, fruehestens
  // 1,2 s nach dem Oeffnen. Tastatur-Aktivierung (Enter/Leertaste auf dem fokussierten Knopf) und synthetische Klicks zaehlen nicht.
  let yesDown = 0;
  for (const ev of ["pointerdown", "touchstart", "mousedown"]) $("apYes").addEventListener(ev, (e) => { if (e.isTrusted) yesDown = Date.now(); }, { passive: true });
  $("apYes").addEventListener("click", (e) => {
    const a = S.approval, age = a ? Date.now() - (a.shownAt || 0) : -1, tapped = e.isTrusted && Date.now() - yesDown < 1500;
    clog(`Karte „Ja“: trusted=${e.isTrusted} getippt=${tapped} detail=${e.detail} nach ${age} ms${a && a.local ? " (lokal)" : ""}`);
    if (a && a.local && (!tapped || age < 1200)) { toast(t("Bitte direkt auf „{b}“ tippen.", { b: $("apYes").textContent })); return; }
    answerApproval("once");
  });
  $("apNo").addEventListener("click", () => answerApproval("deny"));

  // ------------------------------------------------------------------ Gerät (lokaler Gerätedienst über nuorb-shell)
  // Nur vorhanden, wenn die Seite von nuorb-shell auf dem Handy kommt (/device/* -> Gerätedienst auf 127.0.0.1).
  const DEV = { available: null, st: null, err: null };
  // Zwei Schemas: Vertrag nuorb-ui (battery/wifi/…) und Dienst von handy-linux (akku_prozent/wlan_an/…)
  function fromDe(d) {
    const t = Math.max(d.temp_max || 0, d.akku_temp || 0);
    return {
      battery: { percent: d.akku_prozent ?? null, charging: !!d.laedt, status: d.laedt ? "Charging" : "Discharging" },
      wifi: { enabled: !!d.wlan_an, connected: !!(d.wlan_an && (d.wlan_ssid || d.ip)), ssid: d.wlan_ssid || null, signal: d.wlan_signal_prozent ?? null },
      // temp_warn vom Gerätedienst (Akku > 45 °C oder SoC > 80 °C); SoC 50–60 °C unter Last ist normal
      temp: { cpu_c: d.temp_max ?? null, battery_c: d.akku_temp ?? null,
        warn: typeof d.temp_warn === "boolean" ? d.temp_warn : ((d.akku_temp || 0) > 45 || (d.temp_max || 0) > 80) },
      brightness: { percent: d.helligkeit_prozent ?? null }, volume: { percent: d.lautstaerke_prozent ?? null, muted: d.lautstaerke_prozent === 0 },
      screen: { on: d.bildschirm_an !== false }, _de: true,
    };
  }
  function toDe(path, body) {
    switch (path) {
      case "wifi": return ["wlan", { an: !!body.on }];
      case "brightness": return ["helligkeit", { wert: body.percent }];
      case "volume": return ["lautstaerke", { wert: body.muted === true ? 0 : body.percent != null ? body.percent : (S._volBeforeMute || 50) }];
      case "screen": return ["bildschirm", { an: !!body.on }];
      case "reboot": return ["neustart", {}];
      case "poweroff": return ["ausschalten", {}];
    }
    return [path, body];
  }
  async function devCall(path, body) {
    if (DEV.schema === "de") {
      if (path === "volume" && body.muted === true && DEV.st && DEV.st.volume.percent) S._volBeforeMute = DEV.st.volume.percent;
      [path, body] = toDe(path, body || {});
    }
    const r = await fetch("/device/" + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || d.fehler || t("Gerätedienst: Fehler {s}", { s: r.status }));
    clog(`Gerät ${path} ${JSON.stringify(body || {})} -> ok`);
    setTimeout(pollDevice, 400);
    return d;
  }
  async function pollDevice() {
    if (S.features && S.features.geraet === false) { if (DEV.available !== false) { DEV.available = false; renderDevice(); } return; }
    if (DEV.available === false) return;
    try {
      const r = await fetch("/device/status", { cache: "no-store" });
      if (r.status === 404 || !(r.headers.get("content-type") || "").includes("json")) { DEV.available = false; return; }
      const d = await r.json();
      if (!r.ok) { DEV.available = true; DEV.st = null; DEV.err = d.detail || d.fehler || t("Gerätedienst nicht erreichbar"); }
      else { DEV.available = true; DEV.err = null;
        if (d && d.akku_prozent !== undefined) { DEV.schema = "de"; DEV.st = fromDe(d); } else { DEV.schema = "en"; DEV.st = d; } }
    } catch (e) { DEV.err = t("Gerätedienst nicht erreichbar"); }
    renderDevice();
  }
  const pct = (x) => (x == null ? "–" : Math.round(x) + " %");
  function renderDevice() {
    const st = DEV.st, has = !!DEV.available;
    $("devBox").hidden = !has;
    $("sbBat").hidden = !(st && st.battery && st.battery.percent != null);
    if (!st) { renderOffline(); return; }
    const b = st.battery || {}, w = st.wifi || {}, tp = st.temp || {};
    if (b.percent != null) {
      $("batFill").style.width = Math.max(4, Math.min(100, b.percent)) + "%";
      $("batPct").textContent = Math.round(b.percent);
      $("sbBat").dataset.charging = String(!!b.charging); $("sbBat").dataset.low = String(b.percent <= 15 && !b.charging);
    }
    const link = els.chipLink;
    link.dataset.off = String(!w.enabled);
    link.dataset.ok = String(!!w.connected && S.link !== false);
    link.dataset.sig = String(w.signal == null ? 3 : w.signal >= 70 ? 3 : w.signal >= 45 ? 2 : w.signal >= 20 ? 1 : 0);
    link.title = !w.enabled ? t("WLAN aus") : w.connected ? t("WLAN {s}", { s: w.ssid || "" }) : t("WLAN nicht verbunden");
    const hot = !!tp.warn, tc = Math.max(tp.cpu_c || 0, tp.battery_c || 0);
    $("chipTemp").hidden = !hot; $("tempVal").textContent = tc ? Math.round(tc) + "°" : t("heiß"); $("chipTemp").title = tc ? t("Smartphone warm: {c} °C", { c: Math.round(tc) }) : t("Smartphone warm");
    if (hot && !S._hotSaid) { S._hotSaid = true; toast(t("Das Smartphone ist warm ({c} °C).", { c: Math.round(tc) })); }
    if (!hot) S._hotSaid = false;
    $("devLine").textContent = [b.percent != null ? (b.charging ? t("Akku {p} · lädt", { p: pct(b.percent) }) : t("Akku {p}", { p: pct(b.percent) })) : null,
      tp.cpu_c != null ? "CPU " + Math.round(tp.cpu_c) + " °C" : null, w.enabled ? (w.connected ? t("WLAN {s}", { s: w.ssid || t("verbunden") }) : t("WLAN sucht …")) : t("WLAN aus")]
      .filter(Boolean).join(" · ");
    $("tWifi").dataset.on = String(!!w.enabled); $("tWifiSub").textContent = !w.enabled ? t("aus") : w.connected ? (w.ssid || t("verbunden")) : t("sucht …");
    const sb = $("sBright"), sv = $("sVol");
    if (document.activeElement !== sb && st.brightness) { sb.value = st.brightness.percent; $("sBrightV").textContent = pct(st.brightness.percent); }
    if (document.activeElement !== sv && st.volume) { sv.value = st.volume.percent; $("sVolV").textContent = pct(st.volume.percent); $("bMute").dataset.muted = String(!!st.volume.muted); }
    renderOffline();
  }
  function renderOffline() {
    const off = S.link === false, w = DEV.st && DEV.st.wifi;
    $("offlineBox").hidden = !off;
    if (!off) return;
    const btn = $("offlineWifi");
    if (w && !w.enabled) { $("offlineText").textContent = t("WLAN ist aus. Für Sprache und Antworten braucht NuOrb WLAN."); btn.textContent = t("WLAN einschalten"); btn.hidden = false; btn.dataset.act = "wifi"; }
    else if (w && !w.connected) { $("offlineText").textContent = t("WLAN ist an, aber noch nicht verbunden. Suche Netz …"); btn.hidden = true; }
    else { $("offlineText").textContent = t("Der Server ist nicht erreichbar. Gerät und Uhr funktionieren weiter."); btn.textContent = t("Erneut versuchen"); btn.hidden = false; btn.dataset.act = "retry"; }
  }
  $("offlineWifi").addEventListener("click", async () => {
    const btn = $("offlineWifi");
    if (btn.dataset.act === "retry") { pollStatus(); return; }
    btn.disabled = true; $("offlineText").textContent = t("Schalte WLAN ein …");
    try { await devCall("wifi", { on: true }); earcon("up"); } catch (e) { toast(String(e.message || e)); }
    btn.disabled = false;
  });
  // Lokale Bestätigungskarte (gleiches Layout wie Hermes-Freigaben)
  function confirmLocal({ title, desc, facts, yes, say, run }) {
    S.approval = { shownAt: Date.now(), local: async (choice) => { if (choice === "once") await run(); else card("sys", t("Abgebrochen.")); } };
    $("apTitle").textContent = title; $("apDesc").textContent = desc || ""; setFacts(facts || []);
    $("apCmd").textContent = ""; $("apYes").textContent = yes || t("Ja");
    $("approvalBackdrop").hidden = false; earcon("confirm"); if (navigator.vibrate) navigator.vibrate([30, 60, 30]);
    setTimeout(() => $("apNo").focus(), 50); // Tastatur: „Nein“ vorausgewaehlt, Tab -> „Ja“
    if (say) speech.say(say);
  }
  function powerAction(kind) {
    const reboot = kind === "reboot";
    closeSheet("setBackdrop");
    confirmLocal({
      title: reboot ? t("Smartphone neu starten?") : t("Smartphone ausschalten?"),
      desc: reboot ? t("NuOrb ist etwa zwei Minuten weg und startet danach von selbst.") : t("Zum Einschalten danach die Ein-Taste lange drücken."),
      facts: [[t("Ziel"), t("NuOrb-Smartphone (Xiaomi, NixOS)")], [t("Befehl"), reboot ? t("Neustart in 3 s") : t("Ausschalten in 3 s")]],
      yes: reboot ? t("Ja, neu starten") : t("Ja, ausschalten"),
      say: reboot ? t("Soll ich das Smartphone wirklich neu starten?") : t("Soll ich das Smartphone wirklich ausschalten?"),
      run: async () => {
        try {
          await devCall(reboot ? "reboot" : "poweroff", {});
          speech.say(reboot ? t("Bis gleich.") : t("Gute Nacht."));
          $("powerText").textContent = reboot ? t("Smartphone startet neu …") : t("Smartphone wird ausgeschaltet …"); $("powerVeil").hidden = false;
        } catch (e) { card("err", String(e.message || e)); }
      },
    });
  }
  function wifiAction(on) {
    if (on) return devCall("wifi", { on: true }).then(() => { card("sys", t("WLAN eingeschaltet.")); }).catch((e) => card("err", String(e.message || e)));
    confirmLocal({
      title: t("WLAN ausschalten?"), desc: t("Ohne WLAN kann NuOrb nicht sprechen und nicht antworten. Zum Wiedereinschalten erscheint ein großer Knopf."),
      facts: [[t("Ziel"), t("WLAN des Smartphones")], [t("Wieder an"), t("Knopf „WLAN einschalten“ oder Gerät-Panel")]],
      yes: t("Ja, ausschalten"), say: t("Soll ich das WLAN wirklich ausschalten? Dann bin ich offline."),
      run: async () => { try { await devCall("wifi", { on: false }); card("sys", t("WLAN ausgeschaltet.")); } catch (e) { card("err", String(e.message || e)); } },
    });
  }
  $("tWifi").addEventListener("click", () => wifiAction(!(DEV.st && DEV.st.wifi && DEV.st.wifi.enabled)));
  $("tScreen").addEventListener("click", () => { closeSheet("setBackdrop"); devCall("screen", { on: false }).catch((e) => toast(String(e.message || e))); });
  $("tReboot").addEventListener("click", () => powerAction("reboot"));
  $("tOff").addEventListener("click", () => powerAction("poweroff"));
  let slideT = 0;
  const slide = (id, key, path) => {
    const el = $(id);
    el.addEventListener("input", () => {
      $(id + "V").textContent = pct(+el.value);
      clearTimeout(slideT); slideT = setTimeout(() => devCall(path, { percent: +el.value }).catch((e) => toast(String(e.message || e))), 150);
    });
  };
  slide("sBright", "brightness", "brightness"); slide("sVol", "volume", "volume");
  $("bMute").addEventListener("click", (e) => { e.preventDefault(); devCall("volume", { muted: $("bMute").dataset.muted !== "true" }).catch((er) => toast(String(er.message || er))); });

  // Kurzer Gerätestatus fuer Hermes (steht wie die Uhrzeit im input, kostet keinen Prompt-Cache)
  function deviceSummary() {
    const st = DEV.st; if (!st) return null;
    const b = st.battery || {}, w = st.wifi || {}, t = st.temp || {};
    return [b.percent != null ? `Akku ${Math.round(b.percent)} %${b.charging ? ", lädt" : ""}` : null,
      w.enabled ? (w.connected ? "WLAN an" : "WLAN sucht") : "WLAN aus",
      t.warn ? `warm ${Math.round(Math.max(t.cpu_c || 0, t.battery_c || 0))} °C` : null,
      st.brightness ? `Helligkeit ${st.brightness.percent} %` : null,
      st.volume ? (st.volume.muted ? "stumm" : `Lautstärke ${st.volume.percent} %`) : null].filter(Boolean).join(", ");
  }
  S.doneIntents = new Set();
  async function fetchIntent(session, callId) {
    for (let i = 0; i < 8; i++) { // Ergebnis landet ggf. erst kurz nach tool.completed im Verlauf
      try {
        const r = await fetch(`/api/geraet-aktion?session_id=${encodeURIComponent(session)}&tool_call_id=${encodeURIComponent(callId)}`);
        if (r.ok) {
          const d = await r.json();
          if (d.tool_call_id && d.tool_call_id !== callId) { // gueltiges Ergebnis aus einem spaeteren Aufruf – nur einmal ausfuehren
            if (S.doneIntents.has(d.tool_call_id)) return;
          }
          S.doneIntents.add(d.tool_call_id || callId);
          return deviceIntent(d);
        }
        if (r.status !== 404) { clog("Geräteaktion abgelehnt: HTTP " + r.status + " " + (await r.text()).slice(0, 120)); return; }
      } catch (e) { /* weiter */ }
      await new Promise((res) => setTimeout(res, 400 + i * 300));
    }
    clog("Geräteaktion nicht gefunden: " + callId);
  }
  // Von Hermes angeforderte Geräteaktion (MCP „geraet“, Werkzeug „anfordern“) – lokal ausführen, kritische mit Karte
  const INTENT_SAY = { wlan_an: t("Ich schalte das WLAN ein."), wlan_aus: t("Bitte bestätige: WLAN ausschalten."),
    neustart: t("Bitte bestätige den Neustart auf dem Display."), ausschalten: t("Bitte bestätige das Ausschalten auf dem Display."),
    helligkeit: t("Ich stelle die Helligkeit auf {w} Prozent."), lautstaerke: t("Ich stelle die Lautstärke auf {w} Prozent."),
    bildschirm_aus: t("Ich schalte den Bildschirm aus."), bildschirm_an: t("Bildschirm ist an.") }; // {w} bleibt (ohne vars) stehen
  function deviceIntent(a) {
    clog("Hermes fordert Geräteaktion: " + JSON.stringify(a));
    S.lastIntentSay = (INTENT_SAY[a.aktion] || t("Erledige ich.")).replace("{w}", a.wert);
    if (ANDROID) { S.lastIntentSay = t("Gerätebefehle gehen in dieser App nicht."); return; } // Antwort setzt streamRun (fester Satz)
    if (!DEV.available) { card("err", t("Geräteaktion nicht möglich: kein Gerätedienst (läuft die Seite auf dem Smartphone?).")); return; }
    const v = a.wert == null ? null : Math.max(0, Math.min(100, Math.round(+a.wert)));
    const err = (e) => card("err", String(e.message || e));
    switch (a.aktion) {
      case "wlan_an": return wifiAction(true);
      case "wlan_aus": return wifiAction(false);
      case "neustart": return powerAction("reboot");
      case "ausschalten": return powerAction("poweroff");
      case "helligkeit": if (v != null) { const hv = Math.max(5, v); S.lastIntentSay = INTENT_SAY.helligkeit.replace("{w}", hv); // nie ganz schwarz
        return devCall("brightness", { percent: hv }).then(() => card("sys", t("Helligkeit {v} %", { v: hv }))).catch(err); } break;
      case "lautstaerke": if (v != null) return devCall("volume", { percent: v, muted: false }).then(() => card("sys", t("Lautstärke {v} %", { v }))).catch(err); break;
      case "bildschirm_aus": return setTimeout(() => devCall("screen", { on: false }).catch(err), 4000);
      case "bildschirm_an": return devCall("screen", { on: true }).catch(err);
    }
    card("err", t("Unbekannte Geräteaktion: {a}", { a: JSON.stringify(a) }));
  }

  // Sprach-/Textbefehle für das Gerät (lokal, ohne Hermes)
  function deviceCommand(text) {
    if (!DE) return false; // deutsche Muster (Geraet, Wake, Wetter, Haus); auf Englisch entscheidet Hermes
    const lc = " " + text.toLowerCase().replace(/[.!?,]/g, " ") + " ";
    if (wakeCommand(lc, text)) return true; // geht auch ohne Geraetedienst (Schalter liegt auf nuorb)
    if (S.features.zuhause !== false && (homeQuery(lc, text) || weatherCommand(lc, text))) return true;
    if (!DEV.available) return false;
    const say = (msg) => { card("user", text); if (msg) speech.say(msg); return true; };
    let m;
    if (/\b(w-?lan|wifi|wi-fi|internet)\b.*\b(aus|ab|ausschalten|abschalten|deaktivier\w*)\b/.test(lc)) { card("user", text); wifiAction(false); return true; }
    if (/\b(w-?lan|wifi|wi-fi|internet)\b.*\b(an|ein|einschalten|anschalten|aktivier\w*)\b/.test(lc)) { say(t("WLAN geht an.")); wifiAction(true); return true; }
    if (/\b(handy|smartphone|telefon|gerät|system)\b.*\b(neu ?start\w*|neustarten|rebooten)\b|\bneustart\b|\bstart\w*\b.*\b(handy|smartphone|telefon|gerät|system)\b.*\bneu\b/.test(lc)) { card("user", text); powerAction("reboot"); return true; }
    if (/\b(handy|smartphone|telefon|gerät)\b.*\b(ausschalten|abschalten|herunterfahren|runterfahren)\b/.test(lc) || /\b(schalt\w*|fahr\w*)\b.*\b(handy|smartphone|telefon|gerät)\b.*\b(aus|ab|herunter|runter)\b/.test(lc)) { card("user", text); powerAction("poweroff"); return true; }
    if (/\bbildschirm\b.*\b(aus|ausschalten|dunkel)\b/.test(lc)) { say(t("Bildschirm aus. Tippen weckt mich.")); setTimeout(() => devCall("screen", { on: false }).catch(() => {}), 1800); return true; }
    if ((m = lc.match(/\bhelligkeit\b\D{0,12}(\d{1,3})/))) { say(t("Helligkeit {v} Prozent.", { v: m[1] })); devCall("brightness", { percent: +m[1] }).catch((e) => card("err", e.message)); return true; }
    if (/\b(heller)\b/.test(lc) || /\b(dunkler)\b/.test(lc)) {
      const cur = (DEV.st && DEV.st.brightness && DEV.st.brightness.percent) || 50, up = /\bheller\b/.test(lc);
      const v = Math.max(5, Math.min(100, cur + (up ? 20 : -20))); say(up ? t("Heller, {v} Prozent.", { v }) : t("Dunkler, {v} Prozent.", { v }));
      devCall("brightness", { percent: v }).catch((e) => card("err", e.message)); return true;
    }
    if ((m = lc.match(/\blautstärke\b\D{0,12}(\d{1,3})/))) { say(t("Lautstärke {v} Prozent.", { v: m[1] })); devCall("volume", { percent: +m[1] }).catch((e) => card("err", e.message)); return true; }
    if (/\b(lauter|leiser)\b/.test(lc)) {
      const cur = (DEV.st && DEV.st.volume && DEV.st.volume.percent) || 50, up = /\blauter\b/.test(lc);
      const v = Math.max(0, Math.min(100, cur + (up ? 15 : -15)));
      devCall("volume", { percent: v, muted: false }).then(() => say(up ? t("Lauter, {v} Prozent.", { v }) : t("Leiser, {v} Prozent.", { v }))).catch((e) => card("err", e.message)); return true;
    }
    if (/\b(stumm|ton aus)\b/.test(lc)) { card("user", text); devCall("volume", { muted: true }).then(() => card("sys", t("Stumm. Antworten erscheinen nur als Text."))).catch((e) => card("err", e.message)); return true; }
    if (/\b(ton an|laut machen)\b/.test(lc)) { devCall("volume", { muted: false }).then(() => say(t("Ton ist wieder an."))).catch((e) => card("err", e.message)); return true; }
    return false;
  }

  // ------------------------------------------------------------------ Gehirn-Schalter (Umschalten macht nuorb-admin)
  const BR = { data: null, mode: "local", claude: null };
  const MODE_DE = { local: t("Lokal"), auto: t("Automatisch"), remote: "Remote" };
  const fmtUsd = (x) => (Math.round(x * 100) / 100).toLocaleString(LOC) + " $";
  async function loadBrain() {
    try { BR.data = await (await fetch("/api/brain")).json(); } catch (e) { BR.data = { available: false, detail: t("Keine Verbindung.") }; }
    return BR.data;
  }
  function renderBrain() {
    const d = BR.data || {}, models = d.models || {};
    document.querySelectorAll(".br-opt").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.mode === BR.mode)));
    const box = $("brModels"); box.replaceChildren(); box.hidden = BR.mode === "local" || !Object.keys(models).length;
    for (const [id, m] of Object.entries(models)) {
      const b = document.createElement("button"); b.className = "br-model"; b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(id === BR.claude));
      const nm = document.createElement("b"); nm.textContent = modelShort(id, "remote");
      const p = document.createElement("span"); p.textContent = t("{i} / {o}\nje 1 Mio. Token", { i: fmtUsd(m.in), o: fmtUsd(m.out) });
      p.style.whiteSpace = "pre-line"; b.append(nm, p); b.title = m.hint ? t(m.hint) : "";
      b.addEventListener("click", () => { BR.claude = id; renderBrain(); }); box.appendChild(b);
    }
    $("brPrivacy").hidden = BR.mode === "local";
    const cur = d.mode ? t("Aktiv: {m}", { m: (MODE_DE[d.mode] || d.mode) + (d.mode !== "local" && d.claude ? " · " + modelShort(d.claude, "remote") : "") }) : "";
    const m = models[BR.claude];
    $("brNote").textContent = !d.available ? (d.detail || t("Umschalten nur im Admin-UI möglich."))
      : [cur, BR.mode !== "local" && m ? t("{n}: {h} (Eingabe {i}, Ausgabe {o} je 1 Mio. Token)", { n: m.name, h: m.hint ? t(m.hint) : "", i: fmtUsd(m.in), o: fmtUsd(m.out) }) : ""].filter(Boolean).join(" · ");
    $("brApply").disabled = !d.available || (d.mode === BR.mode && (BR.mode === "local" || remembered(BR.mode) === BR.claude));
  }
  // je Modus gemerktes Claude-Modell (nuorb-admin: remote_model / fallback_model)
  function remembered(mode) {
    const d = BR.data || {};
    return (mode === "auto" ? d.fallback_model || d.fallback : d.remote_model) || d.claude || Object.keys(d.models || {})[0] || "claude-haiku-5-5";
  }
  async function openBrain() {
    openSheet("brainBackdrop"); $("brNote").textContent = t("Lade …");
    const d = await loadBrain();
    BR.mode = d.mode || d.ui_mode || "local";
    BR.claude = remembered(BR.mode);
    renderBrain();
  }
  async function switchBrain(mode, claude) {
    const r = await fetch("/api/brain", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, claude }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || t("Umschalten fehlgeschlagen."));
    const label = MODE_DE[mode] + (mode !== "local" ? " · " + modelShort(claude, "remote") : "");
    card("sys", t("Gehirn: {l}", { l: label + (d.effect ? " – " + d.effect : "") }));
    speech.say(mode === "local" ? t("Erledigt. Ich denke jetzt wieder lokal.") : t("Erledigt. Ich nutze jetzt {m}.", { m: modelShort(claude, "remote") }));
    clog("Gehirn umgeschaltet: " + label);
    S._remote = undefined; pollStatus();
  }
  document.querySelectorAll(".br-opt").forEach((b) => b.addEventListener("click", () => { BR.mode = b.dataset.mode; BR.claude = remembered(BR.mode); renderBrain(); }));
  $("chipBrain").addEventListener("click", openBrain);
  $("brCancel").addEventListener("click", () => closeSheet("brainBackdrop"));
  $("brainBackdrop").addEventListener("click", (e) => { if (e.target.id === "brainBackdrop") closeSheet("brainBackdrop"); });
  $("brApply").addEventListener("click", async () => {
    $("brApply").disabled = true; $("brNote").textContent = t("Schalte um …");
    try { await switchBrain(BR.mode, BR.mode === "local" ? null : BR.claude); closeSheet("brainBackdrop"); }
    catch (e) { $("brNote").textContent = String(e.message || e); $("brApply").disabled = false; }
  });

  // Sprach-/Textbefehl: „NuOrb, wechsel auf Sonnet“, „zurück auf lokal“, „schalte auf automatisch“ -> Bestätigungskarte
  // ------------------------------------------------------------------ Name des Assistenten und Begruessung
  // assistant_name (ui.json, nuorb-admin) = wie der Assistent heisst; Marke/Weckwort bleiben davon unberuehrt.
  // Umbenennen per Sprache („Ab jetzt heisst du Max“, „Nenn dich Max“, „call yourself Max“) oder Panel-Feld, ohne Karte.
  const NAME_DE = /\b(?:ab jetzt |von jetzt an |ab sofort )?(?:heißt du|heisst du|nenn(?:e)? dich|dein name (?:ist|lautet|soll)|ich (?:nenne|taufe) dich)\s+(?:jetzt\s+|ab jetzt\s+|einfach\s+)?([a-zäöüß][a-zäöüß0-9-]{0,23})/i;
  const NAME_EN = /\b(?:call yourself|your name is|from now on you(?:'re| are)|i(?:'ll| will) call you|i name you)\s+([a-z][a-z0-9-]{0,23})/i;
  const NAME_STOP = /^(sein|werden|heißen|heissen|be|now|du|dich|so|wie|was|jetzt|nicht|not)$/i;
  const USERNAME_RE = DE ? /\b(ich bin|ich heiße|ich heisse|nenn mich|mein name ist)\b/i : /\b(i am|i'm|call me|my name is)\b/i;
  const KEEP_RE = DE ? /^(passt( so)?|behalt\w*|bleib\w*( so)?|ok(ay)?|gut so|ist gut|gefällt mir|lass( es)? so|nein danke)\b/i : /^(keep( it)?|that'?s fine|fine|ok(ay)?|it'?s fine|i like it|no thanks?)\b/i;
  const ONB = { awaiting: false, started: false };
  async function setAssistantName(n) {
    n = String(n || "").trim(); n = n.charAt(0).toUpperCase() + n.slice(1);
    const r = await fetch("/api/assistant", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ assistant_name: n }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || t("Fehler {s}", { s: r.status }));
    if (window.I18N) { I18N.setName(n); I18N.reapply(); }
    $("optName").value = n; clog("Assistentenname: " + n);
    return n;
  }
  function nameCommand(text) {
    const m = String(text).match(DE ? NAME_DE : NAME_EN) || (!DE ? null : String(text).match(NAME_EN));
    if (!m || NAME_STOP.test(m[1])) return false;
    card("user", text);
    setAssistantName(m[1]).then((n) => {
      ONB.awaiting = false;
      if (USERNAME_RE.test(text)) { S.busy = false; ask(text, false, true); return; } // Nutzername merkt sich Hermes (Gedaechtnis)
      speech.say(t("Alles klar, ab jetzt heiße ich {n}.", { n }) + (wakeAvailable() ? " " + t("Wecken kannst du mich weiterhin mit „Hey NuOrb“.") : ""));
    }).catch((e) => card("err", String(e.message || e)));
    return true;
  }
  function greet(again) {
    ONB.started = true; ONB.awaiting = true;
    const n = window.I18N ? I18N.name : "NuOrb";
    const txt = t("Hallo! Mein Schöpfer hat mich {n} getauft. Falls dir das zu kompliziert ist, sag mir einfach, wie du mich nennen möchtest.", { n })
      + (wakeAvailable() ? " " + t("Wecken kannst du mich mit „Hey NuOrb“.") : "") + " " + t("Und wie darf ich dich nennen?");
    card("ai", txt); view("talk");
    if (opts.follow) { CONV.active = true; CONV.rounds = 0; CONV.lastAt = Date.now(); CONV.prompted = true; }
    speech.say(txt);
    if (!again) fetch("/api/assistant", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ onboarded: true }) }).catch(() => {});
    clog("Begrüßung" + (again ? " (wiederholt)" : ""));
  }
  // Antwort auf die Begruessung bzw. Bitte um Vorstellung
  function onboardCommand(text) {
    const lc = String(text).toLowerCase().trim();
    if ((DE ? /\bstell dich (noch ?mal |nochmal |erneut )?vor\b|\bwer bist du\b/ : /\bintroduce yourself( again)?\b|\bwho are you\b/).test(lc)) { card("user", text); greet(true); return true; }
    if (!ONB.awaiting) return false;
    if (KEEP_RE.test(lc.replace(/[.!?,]/g, "")) && !USERNAME_RE.test(lc)) {
      ONB.awaiting = false; card("user", text);
      speech.say(t("Gut, dann bleibe ich {n}.", { n: window.I18N ? I18N.name : "NuOrb" })); return true;
    }
    if (USERNAME_RE.test(lc)) { ONB.awaiting = false; return false; } // geht an Hermes (merkt sich den Namen)
    ONB.awaiting = false; return false;
  }
  function localCommand(text) {
    return onboardCommand(text) || nameCommand(text) || deviceCommand(text) || brainCommand(text);
  }
  $("optName").value = window.I18N ? I18N.name : "";
  $("optName").addEventListener("change", () => {
    const el = $("optName"), v = el.value.trim();
    if (!v || v === (window.I18N ? I18N.name : "")) return;
    setAssistantName(v).then((n) => toast(t("Ich heiße jetzt {n}.", { n }))).catch((e) => { el.value = window.I18N ? I18N.name : ""; toast(String(e.message || e)); });
  });

  function brainCommand(text) {
    if (!DE) return false; // deutsche Muster; auf Englisch entscheidet Hermes
    const lc = text.toLowerCase().replace(/[.!?,]/g, " ");
    const m = lc.match(/\b(wechs[el]\w*|schalt\w*|stell\w*|geh\w*|nimm|nutze?|benutze?|zurück)\b.{0,20}?\b(auf|zu|zur|zum)?\s*(lokal\w*|gemma|automatisch\w*|auto|sonnet|haiku|opus|claude|remote)\b/);
    if (!m) return false;
    const named = lc.match(/\b(sonnet|haiku|opus)\b/);
    const w = named ? named[1] : m[3];
    const mode = /^lokal|^gemma/.test(w) ? "local" : /^auto/.test(w) ? "auto" : "remote";
    const known = (BR.data && BR.data.models) || {};
    const pick = (n) => Object.keys(known).find((id) => id.includes(n)) || `claude-${n}-5-5`;
    const claude = /sonnet|haiku|opus/.test(w) ? pick(w) : remembered(mode);
    const name = MODE_DE[mode] + (mode !== "local" ? " · " + modelShort(claude, "remote") : "");
    card("user", text);
    const info = known[claude];
    S.approval = { shownAt: Date.now(), local: async (choice) => {
      if (choice !== "once") { card("sys", t("Gehirn bleibt, wie es ist.")); return; }
      try { await switchBrain(mode, mode === "local" ? null : claude); }
      catch (e) { card("err", String(e.message || e)); speech.say(t("Das hat nicht geklappt.") + " " + String(e.message || "")); }
    } };
    $("apTitle").textContent = t("Gehirn wechseln?");
    $("apDesc").textContent = mode === "local" ? t("Alles bleibt im Haus. Braucht den PC mit Gemma.")
      : t("Datenschutz: Die Gesprächstexte gehen an Anthropic (USA). Audio bleibt lokal auf deinem Server.");
    setFacts([[t("Neu"), name], info ? [t("Preis"), t("Eingabe {i}, Ausgabe {o} je 1 Mio. Token", { i: fmtUsd(info.in), o: fmtUsd(info.out) })] : null,
      mode === "auto" ? [t("Ablauf"), t("Gemma, wenn der PC läuft – sonst {m}", { m: modelShort(claude, "remote") })] : null].filter(Boolean));
    $("apCmd").textContent = ""; $("apYes").textContent = t("Ja, wechseln");
    $("approvalBackdrop").hidden = false; view("talk"); earcon("confirm");
    speech.say(mode === "local" ? t("Soll ich zurück auf das lokale Gehirn wechseln?")
      : t("Soll ich auf {m} wechseln? Die Gesprächstexte gehen dann an Anthropic.", { m: modelShort(claude, "remote") }));
    loadBrain(); // Preise/Verfügbarkeit nachladen
    return true;
  }

  // ------------------------------------------------------------------ Texteingabe, Neu, Einstellungen
  const openSheet = (id) => { $(id).hidden = false; };
  const closeSheet = (id) => { $(id).hidden = true; };
  $("kbdBtn").addEventListener("click", () => { openSheet("kbdBackdrop"); setTimeout(() => $("kbdInput").focus(), 50); });
  $("kbdBackdrop").addEventListener("click", (e) => { if (e.target.id === "kbdBackdrop") closeSheet("kbdBackdrop"); });
  $("kbdForm").addEventListener("submit", (e) => {
    e.preventDefault(); const txt = $("kbdInput").value.trim(); if (!txt) return;
    $("kbdInput").value = ""; closeSheet("kbdBackdrop"); audio();
    if (localCommand(txt)) return;
    if (S.brain === false) { offlineReply(); return; }
    interrupt(true); ask(txt);
  });
  $("newBtn").addEventListener("click", () => {
    interrupt(true); S.session = null; store.set("session", null);
    els.convo.replaceChildren(); view("home"); restingState(); toast(t("Neues Gespräch."));
  });
  const openDev = () => { openSheet("setBackdrop"); pollDevice(); };
  $("clockMini").addEventListener("click", openDev);
  $("sbDev").addEventListener("click", openDev);
  $("setClose").addEventListener("click", () => closeSheet("setBackdrop"));
  $("setBackdrop").addEventListener("click", (e) => { if (e.target.id === "setBackdrop") closeSheet("setBackdrop"); });
  // ------------------------------------------------------------------ „Hey NuOrb“ (Wake-Word-Dienst von handy-linux)
  // Schalter: ui.json wake_word (nuorb-admin). Die UI spiegelt ihn an den Dienst (/wake/aktiv) und hoert auf /wake/events.
  // Ein Wake-Ereignis wirkt wie Tippen: Freihand-Aufnahme mit Pausen-Erkennung. Datenschutz liegt beim Dienst (nur RAM-Puffer).
  const WAKE = { on: null, es: null, svc: null, synced: 0, retry: null };
  // Gibt es hier ueberhaupt ein Weckwort? Kiosk (nuorb-shell mit Wake-Dienst) ja; Android-App laut Bruecke
  // (wakeVerfuegbar, fehlt bei App < 1.2.0 -> ja); normaler Browser nein.
  function wakeAvailable() {
    // Android: nur ein ausdrueckliches „ja“ der Bruecke zaehlt (Store-Fassungen ohne Weckwort liefern false; Strings wie
    // „false“/„0“ waeren in JS wahr, deshalb streng auswerten). Fehlt die Methode, gibt es kein Weckwort.
    if (ANDROID) {
      try {
        if (!NATIVE || typeof NATIVE.wakeVerfuegbar !== "function") return false;
        const v = NATIVE.wakeVerfuegbar();
        return v === true || v === 1 || /^(true|1|ja|yes)$/i.test(String(v));
      } catch (e) { return false; }
    }
    return DEV.available === true;
  }
  function renderWake() {
    const avail = wakeAvailable(), row = $("wakeRow"), soon = !avail && ANDROID;
    // Ohne Weckwort: im Browser ausblenden; in der App (Store-Fassung) ausgegraut mit „bald verfuegbar“ in derselben Zeile
    row.hidden = !avail && !ANDROID; $("wakeInfo").hidden = !avail;
    $("optWake").disabled = !avail; row.classList.toggle("is-off", soon); $("wakeSoon").hidden = !soon;
    if (soon) { $("optWake").checked = false; return; }
    $("optWake").checked = !!WAKE.on;
    const info = $("wakeInfo").firstElementChild;
    info.textContent = ANDROID ? (NATIVE ? (WAKE.on ? t("aktiv (App)") : "") : t("nur in der App")) : DEV.available === false ? t("nur am Smartphone") : WAKE.on && WAKE.svc === false ? t("Wake-Dienst fehlt") : WAKE.on && WAKE.svc ? t("aktiv") : "";
  }
  function wakeApply(on) {
    if (ANDROID) { // Wake gehoert der App, nicht ui.json (sonst schaltet das Xiaomi sein Mikro)
      let n = false; try { n = !!(NATIVE && NATIVE.getWake && NATIVE.getWake()); } catch (e) { /* egal */ }
      if (n !== WAKE.on) { WAKE.on = n; WAKE.svc = !!NATIVE; renderWake(); }
      return;
    }
    if (DEV.available === null) return; // noch unklar, ob wir im Kiosk (nuorb-shell) laufen
    const changed = on !== WAKE.on; WAKE.on = on;
    if (DEV.available && (changed || Date.now() - WAKE.synced > 60000)) {
      WAKE.synced = Date.now();
      fetch("/wake/aktiv", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ an: on }) })
        .then((r) => { WAKE.svc = r.ok; if (!r.ok && changed) clog("Wake-Dienst /aktiv: HTTP " + r.status); renderWake(); })
        .catch(() => { WAKE.svc = false; renderWake(); });
      if (on) wakeConnect(); else wakeClose();
    }
    if (changed) renderWake();
  }
  function wakeClose() { if (WAKE.es) { WAKE.es.close(); WAKE.es = null; } clearTimeout(WAKE.retry); }
  function wakeConnect() {
    if (WAKE.es || !window.EventSource) return;
    const es = WAKE.es = new EventSource("/wake/events");
    es.onopen = () => { WAKE.svc = true; renderWake(); };
    es.addEventListener("wake", (e) => { let d = {}; try { d = JSON.parse(e.data); } catch (x) { /* egal */ } onWake(d); });
    es.onerror = () => { if (es.readyState === 2) { WAKE.es = null; WAKE.svc = false; renderWake(); clearTimeout(WAKE.retry); WAKE.retry = setTimeout(() => { if (WAKE.on) wakeConnect(); }, 30000); } };
  }
  // Sprachbefehl „Schalte Hey NuOrb ein/aus“, „Hey NuOrb aus“, „Weckwort an“. Einschalten nur mit Karte (Mikro hoert dann staendig).
  const WAKE_SELF = String(window.I18N ? I18N.wake : "Hey NuOrb").toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
  const WAKE_NAME = "(?:" + WAKE_SELF + "|hey\\s+nuorb|wake\\s*-?\\s*word|weckwort|weckfunktion|aufwecken)";
  const WAKE_RE1 = new RegExp(`\\b${WAKE_NAME}\\s+(an|ein|aus|ab|einschalten|anschalten|ausschalten|abschalten|aktivieren|deaktivieren)\\s*$`);
  const WAKE_RE2 = new RegExp(`\\b(schalt\\w*|mach\\w*|stell\\w*|aktivier\\w*|deaktivier\\w*)\\b.*\\b${WAKE_NAME}\\b(.*)$`);
  function wakeCommand(lc, text) {
    let m = lc.trim().match(WAKE_RE1), on;
    if (m) on = !/^(aus|ab|ausschalten|abschalten|deaktivieren)$/.test(m[1]);
    else if ((m = lc.match(WAKE_RE2)) && (/\b(an|ein|aus|ab)\b/.test(m[2]) || /aktivier/.test(m[1]))) on = /deaktivier/.test(m[1]) ? false : /aktivier/.test(m[1]) ? true : /\b(an|ein)\b/.test(m[2]);
    else return false;
    card("user", text);
    if (!wakeAvailable()) { speech.say(t("Ein Weckwort gibt es hier noch nicht. Tipp einfach auf den Knopf, um mit mir zu sprechen.")); return true; }
    const go = async () => {
      if (ANDROID) {
        if (!NATIVE || !NATIVE.setWake) { card("err", t("„Hey NuOrb“ gibt es hier nur in der NuOrb-App.")); return; }
        try { if (NATIVE.setWake(on) === false) throw new Error("abgelehnt"); } catch (e) { card("err", t("Umschalten fehlgeschlagen.")); return; }
        WAKE.on = on; renderWake(); speech.say(on ? t("Erledigt. Sag einfach Hey NuOrb, wenn du mich brauchst.") : t("Hey NuOrb ist aus. Zum Sprechen tippen.")); return;
      }
      const r = await fetch("/api/wake", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ an: on }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { card("err", d.detail || t("Umschalten fehlgeschlagen.")); return; }
      wakeApply(on); speech.say(on ? t("Erledigt. Sag einfach Hey NuOrb, wenn du mich brauchst.") : t("Hey NuOrb ist aus. Zum Sprechen tippen."));
    };
    if (!on) { go(); return true; }
    if (WAKE.on) { speech.say(t("Hey NuOrb ist schon an.")); return true; }
    confirmLocal({ title: t("„Hey NuOrb“ einschalten?"), desc: t("Das Mikro hört dann ständig mit. Nichts wird gespeichert oder gesendet, bevor „Hey NuOrb“ erkannt ist."),
      facts: [[t("Ziel"), t("Wake-Word auf dem Smartphone")], [t("Aus"), t("„Hey NuOrb aus“ oder Gerät-Panel")]], yes: t("Ja, einschalten"),
      say: t("Soll ich Hey NuOrb einschalten? Dann höre ich ständig mit."), run: go });
    return true;
  }
  // Wetter immer von der eigenen Station (deterministisch, ohne Modell): /api/wetter -> fertiger Sprechsatz
  const WX_WORDS = /\b(wetter\w*|wie (warm|kalt)|wie viel grad|wieviel grad|grad (hat|haben|sind|ist) es|temperatur draußen|draußen (warm|kalt)|regnet( es)?|regnen|regen|regenschirm|schneit|schneien|schnee|frost|glätte|glatteis|wind\w*|sturm|gewitter)\b/;
  const WX_NOT = /\b(handy|smartphone|akku|cpu|prozessor|gerät|pc|rechner|telefon|windows|wecker)\b/;
  // Haus (nur LESEN, lokal ueber /api/zuhause): Heizung/Puffer/Laddomat/Pumpen/Ofen, Raeume, Klima, Energie.
  // Schreibsaetze (stell/mach/schalt…, waermer/kaelter, „auf 22 Grad“) gehen bewusst an Hermes (Haiku-Weiche), damit Karten greifen.
  const HOME_WRITE = /\b(stelle?n?|stellst|setze?n?|mache?n?|machst|schalte?n?|schaltest|drehe?n?|erhöh\w*|senk\w*|reduzier\w*|wärmer|kälter|heiz\w* (auf|hoch)|kühl\w* (auf|runter)|auf \d+(,\d)? ?grad|an ?machen|aus ?machen|einschalten|ausschalten)\b/;
  const ROOMS = [[/\bbad(ezimmer)?\b/, "Bad"], [/\bschlafzimmer\b/, "Schlafzimmer"], [/\bküche\b/, "Küche"], [/\bflur\b/, "Flur"],
    [/\bgäste.?(wc|klo|toilette)\b/, "Gäste WC"]];
  // Eigene Raumnamen (z. B. Kinderzimmer nach Namen) kommen aus /api/status „rooms“ – nie fest im Code
  function setRooms(list) {
    for (const name of list || []) {
      const low = String(name).toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (!ROOMS.some(([re, n]) => n === name || re.test(" " + String(name).toLowerCase() + " "))) ROOMS.push([new RegExp(`\\b${low}s?\\b`), name]);
    }
  }
  function homeQuery(lc, text) {
    if (HOME_WRITE.test(lc) || /\b(handy|smartphone|telefon|akku)\b/.test(lc)) return false;
    const room = (ROOMS.find(([re]) => re.test(lc)) || [])[1] || "";
    let w = null, args = {};
    let m;
    if ((m = lc.match(/\bpuffer\s*(eins|zwei|1|2)?\s*(oben|mitte|unten)?/))) {
      w = "heizung"; const n = { eins: 1, zwei: 2, 1: 1, 2: 2 }[m[1]]; args.was = ["Puffer", n, m[2]].filter(Boolean).join(" ");
    } else if (/\bladdomat\b/.test(lc)) { w = "heizung"; args.was = "Laddomat"; }
    else if (/\bpumpen?\b/.test(lc)) { w = "heizung"; args.was = "Pumpen"; }
    else if (/\b(holz)?ofen\b/.test(lc)) { w = "heizung"; args.was = "Ofen"; }
    else if (/\bheizkreis\w*\s*(fbh|fußboden\w*)/.test(lc)) { w = "heizung"; args.was = "Heizkreis FBH"; }
    else if (/\bheizung\b/.test(lc)) { w = "heizung"; }
    else if (/\bklima\w*\b/.test(lc)) { w = "klima"; if (room) args.geraet = room === "Bad" ? "Badezimmer" : room; }
    else if (/\b(solar\w*|photovoltaik|pv|batterie|hausspeicher|einspeis\w*|netzbezug|stromverbrauch|strom|energie)\b/.test(lc)) w = "energie";
    else if ((room || /\b(räume|räumen|zimmern|im haus|drinnen)\b/.test(lc)) && /\b(warm|kalt|grad|temperatur|wie viel)\b/.test(lc)) { w = "raeume"; if (room) args.raum = room; }
    if (!w) return false;
    card("user", text);
    S.busy = true; setState("thinking", t("Haus …"));
    fetch("/api/zuhause", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ werkzeug: w, args }) })
      .then((r) => r.json()).catch(() => ({ ok: false, satz: t("Das Haus ist gerade nicht erreichbar.") }))
      .then((d) => {
        S.busy = false; const satz = d.satz || d.detail || t("Das Haus ist gerade nicht erreichbar.");
        card("ai", satz); clog(`Haus ${w} ${JSON.stringify(args)} lokal: ${d.ok ? "ok" : "Fehler"}`);
        if (opts.voice) speech.say(satz); else { restingState(); convCheck(); }
      });
    return true;
  }
  function weatherCommand(lc, text) {
    if (!WX_WORDS.test(lc) || WX_NOT.test(lc)) return false;
    const zr = /übermorgen|uebermorgen/.test(lc) ? "uebermorgen" : /\bmorgen\b/.test(lc) ? "morgen"
      : /wochenende|\bwoche\b|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|nächsten tage|kommenden tage/.test(lc) ? "woche"
      : /\bheute\b|heute abend|heute nachmittag|\bnoch\b/.test(lc) ? "heute" : "jetzt";
    card("user", text);
    S.busy = true; setState("thinking", t("Wetterstation …"));
    fetch("/api/zuhause", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ werkzeug: "wetter", args: { zeitraum: zr } }) })
      .then((r) => r.json()).catch(() => ({ ok: false, satz: t("Die Wetterstation ist gerade nicht erreichbar.") }))
      .then((d) => {
        S.busy = false; const satz = d.satz || t("Die Wetterstation ist gerade nicht erreichbar.");
        card("ai", satz); clog(`Wetter (${zr}) lokal: ${d.ok ? "ok" : "ohne Station"}`);
        if (opts.voice) speech.say(satz); else { restingState(); convCheck(); }
      });
    return true;
  }
  window.addEventListener("nuorb-wake", (e) => { if (ANDROID) onWake((e && e.detail) || {}); });
  if (NATIVE) new MutationObserver(nativeState).observe($("approvalBackdrop"), { attributes: true, attributeFilter: ["hidden"] });
  function onWake(d) {
    clog(`Wake: ${d.wort || "?"} ${d.score != null ? Number(d.score).toFixed(2) : ""} (Zustand ${S.state})`);
    if (!WAKE.on || S.approval || S.state === "listening" || rec.starting) return;
    if (speech.active || Date.now() - (speech.endedAt || 0) < 1500) { clog("Wake ignoriert (Sprachausgabe)"); return; }
    if (S.busy) return; // Antwort laeuft noch
    CONV.active = false;
    if (DEV.st && DEV.st.screen && DEV.st.screen.on === false) devCall("screen", { on: true }).catch(() => {});
    handsFree("Weckwort");
  }
  $("optFollow").addEventListener("change", async () => {
    const el = $("optFollow"), an = el.checked;
    try {
      const r = await fetch("/api/setting", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ follow_up: an }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || t("Fehler {s}", { s: r.status }));
      opts.follow = an; if (!an) convEnd("ausgeschaltet"); toast(an ? t("NuOrb hört nach jeder Antwort kurz weiter zu.") : t("Nach der Antwort: wieder Tippen oder „Hey NuOrb“."));
    } catch (e) { el.checked = !an; toast(String(e.message || e)); }
  });
  // NuOrb-App: native Einstellungen (Entkoppeln, Neu koppeln, Sprache, Updates) – Bruecke einstellungen(), seit App 1.0
  if (NATIVE && typeof NATIVE.einstellungen === "function") {
    $("appSettings").hidden = false;
    $("appSettings").addEventListener("click", () => { try { NATIVE.einstellungen(); } catch (e) { toast(t("Umschalten fehlgeschlagen.")); } });
  }
  $("wakeRow").addEventListener("click", () => { if (!wakeAvailable()) toast(t("Weckwort kommt mit einem Update. Bis dahin: Orb antippen.")); });
  $("optWake").addEventListener("change", async () => {
    const el = $("optWake"), an = el.checked;
    if (ANDROID) {
      try { if (!NATIVE || !NATIVE.setWake) throw new Error(t("Nur in der NuOrb-App.")); if (NATIVE.setWake(an) === false) throw new Error(t("Umschalten fehlgeschlagen.")); WAKE.on = an; renderWake(); toast(an ? t("„Hey NuOrb“ ist an.") : t("„Hey NuOrb“ ist aus.")); }
      catch (e) { el.checked = !an; toast(String(e.message || e)); }
      return;
    }
    try {
      const r = await fetch("/api/wake", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ an }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || t("Fehler {s}", { s: r.status }));
      wakeApply(an); toast(an ? t("„Hey NuOrb“ ist an.") : t("„Hey NuOrb“ ist aus."));
    } catch (e) { el.checked = !an; toast(String(e.message || e)); }
  });

  const bindOpt = (id, key, fn) => { const el = $(id); el.checked = opts[key]; el.addEventListener("change", () => { opts[key] = el.checked; store.set(key, el.checked); fn && fn(el.checked); }); };
  bindOpt("optVoice", "voice", (v) => { if (!v) speech.stop(); });
  bindOpt("optCalm", "calm", (v) => { app.dataset.calm = String(v); Orb.calm(v || matchMedia("(prefers-reduced-motion: reduce)").matches); });
  bindOpt("optEarcons", "earcons");
  bindOpt("optMicviz", "micviz");
  app.dataset.calm = String(opts.calm); if (opts.calm) Orb.calm(true);

  // Element-Vollbild (blendet Epiphanys Leiste aus). Braucht eine Nutzergeste: das Kiosk-Skript sendet nach
  // dem Laden F13 per wtype; jeder Tipp holt das Vollbild auch nach einem Verlassen zurueck.
  function goFullscreen() {
    if (ANDROID) return; // die App macht Immersive-Modus nativ
    const d = document, el = d.documentElement;
    if (d.fullscreenElement || d.webkitFullscreenElement) return;
    try {
      const p = el.requestFullscreen ? el.requestFullscreen({ navigationUI: "hide" }) : el.webkitRequestFullscreen && el.webkitRequestFullscreen();
      if (p && p.catch) p.catch(() => {});
    } catch (e) { /* ohne Vollbild weiter */ }
  }
  document.addEventListener("keydown", (e) => { if (e.key === "F13" || e.code === "F13") e.preventDefault(); goFullscreen(); }, true);
  // Tasten fuer Hardware-Knoepfe/Fernsteuerung (wtype): F14 = Sprechen an/aus (wie kurzes Tippen), F15 = Texteingabe
  document.addEventListener("keydown", (e) => {
    const k = e.key || e.code;
    if (k === "F14") {
      e.preventDefault(); audio(); unlockAudio();
      if (S.state === "listening") stopRec();
      else if (S.busy || speech.active) { interrupt(true); restingState(); }
      else handsFree();
      clog("Taste F14 (Sprechen)");
    } else if (k === "F15") {
      e.preventDefault(); openSheet("kbdBackdrop"); setTimeout(() => $("kbdInput").focus(), 50); clog("Taste F15 (Texteingabe)");
    }
  });
  document.addEventListener("pointerdown", goFullscreen, true);

  // Bildschirm anlassen, solange die Seite sichtbar ist (falls der Browser es kann)
  let wakeLock = null;
  async function keepAwake() { try { if (navigator.wakeLock && !wakeLock) { wakeLock = await navigator.wakeLock.request("screen"); wakeLock.addEventListener("release", () => { wakeLock = null; }); } } catch (e) { /* egal */ } }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { keepAwake(); pollStatus(); } });
  document.addEventListener("pointerdown", keepAwake, { once: true });

  // Testhaken fuer Screenshots: ?demo=listening|thinking|speaking|offline|approval|talk
  function demo(mode) {
    const add = () => { card("user", t("Wie voll ist die Festplatte auf dem Server?")); const c = toolChip("terminal", "df -h /"); c.classList.add("done");
      card("ai", t("Auf dem Server sind 11 von 32 Gigabyte belegt, also rund ein Drittel. Genug Platz für ein paar Jahrzehnte Notizen.")); };
    if (mode === "talk" || mode === "speaking" || mode === "thinking" || mode === "approval") add();
    if (mode === "approval") showApproval("demo", { description: "Hermes will einen Ordner rekursiv löschen.", command: "rm -rf ~/projekte/alt-backup" });
    if (mode === "approval-claude") { add(); showApproval("demo", { title: "MCP server 'claude' is asking", command: "MCP tool 'auftrag' on UNTRUSTED server 'claude' wants to run. Costs 5-100 Cent (Claude Sonnet 5.5, lesen und schreiben).\nArguments: {\"auftrag\": \"Mach die Uhr auf dem Startbildschirm etwas größer.\"}", description: "Server 'claude' is configured 'trust: untrusted'." }); mode = "approval"; }
    if (mode === "approval-klima") { add(); showApproval("demo", { command: "MCP tool 'klima_stellen' on UNTRUSTED server 'zuhause_schalten' wants to run.\nArguments: {\"geraet\": \"Schlafzimmer\", \"an\": true, \"modus\": \"heizen\", \"soll\": 22, \"luefter\": \"auto\"}" }); mode = "approval"; }
    if (mode === "offline") { S.brain = false; els.chipBrain.dataset.ok = "false"; els.chipBrain.querySelector(".chip-label").textContent = t("Gehirn offline"); }
    S.demo = mode;
    setState(mode === "talk" || mode === "approval" ? "thinking" : mode, mode === "thinking" ? "Terminal …" : undefined);
    if (mode === "approval") S.busy = true;
    if (mode === "listening") { app.dataset.mic = "on"; view("talk"); let t = 0; setInterval(() => { t += .1; const l = .35 + .3 * Math.sin(t * 3) * Math.sin(t * 1.3); Orb.set({ level: l }); els.pttLevel.style.strokeDashoffset = String(352 - 352 * l); }, 50); }
    if (mode === "speaking") { let t = 0; setInterval(() => { t += .1; Orb.set({ level: .3 + .3 * Math.abs(Math.sin(t * 4.1) * Math.sin(t * 1.7)) }); }, 50); }
  }

  // ------------------------------------------------------------------ Selbst-Update
  // Alle 60 s Build-Kennung pruefen; bei neuer Version neu laden – aber nur in Ruhe (keine Aufnahme, kein Run,
  // keine Sprachausgabe, keine offene Karte/Panel). Kiosk hat keine Neu-laden-Taste.
  const BUILD = document.documentElement.dataset.build || "";
  let pendingBuild = null;
  const quiet = () => !S.busy && !S.run && !rec.mr && !rec.starting && !speech.active && !S.approval &&
    ["idle", "offline"].includes(S.state) && [...document.querySelectorAll(".sheet-backdrop")].every((x) => x.hidden);
  async function checkVersion() {
    try {
      const v = await (await fetch("/api/version", { cache: "no-store" })).json();
      if (BUILD && v.build && v.build !== BUILD) pendingBuild = v.build;
    } catch (e) { /* offline */ }
    if (pendingBuild && quiet()) { clog(`Neue Version ${pendingBuild} (war ${BUILD}) – lade neu`); setTimeout(() => location.reload(), 300); }
  }
  if (BUILD) { setInterval(checkVersion, 60000); setInterval(() => { if (pendingBuild && quiet()) checkVersion(); }, 5000); }

  // ------------------------------------------------------------------ Start
  tick(); setInterval(tick, 1000);
  setState("idle", "");
  levelLoop();
  const dm = new URLSearchParams(location.search).get("demo");
  if (dm) { pollStatus().then(() => demo(dm)); loadWidgets(); }
  else { const first = pollStatus(); setInterval(() => { if (!S.demo) pollStatus(); }, 5000); loadWidgets(); setInterval(loadWidgets, 60000);
    loadBrain(); setInterval(loadBrain, 60000);
    // Geraetedienst erst nach dem ersten Status fragen: bei features.geraet === false gar nicht (kein 404 im Image)
    first.finally(() => { pollDevice(); setInterval(() => { if (DEV.available !== false) pollDevice(); }, 5000); }); }
  window.NuOrb = { S, ask, speech, demo };
})();
