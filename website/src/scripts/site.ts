// NuOrb website – kleines Client-Skript ohne Abhängigkeiten.
// Keine Netzwerkanfragen außer eigenen Mediendateien, kein Mikrofon, keine Cookies.
// Einziger Speicher: localStorage "nuorb-lang" (gewählte Sprache), nur im Browser.

type OrbApi = { set(o: { state?: string; level?: number }): void; calm(v: boolean): void; renderer?: string };
declare global { interface Window { Orb?: OrbApi } }

const root = document.documentElement;
root.classList.add("js");
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const LS = "nuorb-lang";
const store = {
  get(): string | null { try { return localStorage.getItem(LS); } catch { return null; } },
  set(v: string) { try { localStorage.setItem(LS, v); } catch { /* privat/gesperrt: egal */ } },
};

// Sprachwahl merken; auf "/" nur einer früher getroffenen Wahl folgen
document.querySelectorAll<HTMLAnchorElement>("a[data-lang]").forEach((a) => a.addEventListener("click", () => store.set(a.dataset.lang!)));
if (document.querySelector("[data-picker]")) {
  const l = store.get();
  if (l === "en" || l === "de") location.replace(`/${l}/`);
}

// Navigation: Hintergrund beim Scrollen
const nav = document.querySelector<HTMLElement>("[data-nav]");
if (nav) {
  const on = () => nav.classList.toggle("is-scrolled", scrollY > 8);
  on(); addEventListener("scroll", on, { passive: true });
}

// Mobiles Menü
const menu = document.querySelector<HTMLElement>("[data-menu]");
const opener = document.querySelector<HTMLButtonElement>("[data-menu-open]");
if (menu && opener) {
  const focusables = () => Array.from(menu.querySelectorAll<HTMLElement>("a, button"));
  const close = (focus = true) => {
    menu.hidden = true; opener.setAttribute("aria-expanded", "false"); document.body.style.overflow = "";
    if (focus) opener.focus();
  };
  const open = () => {
    menu.hidden = false; opener.setAttribute("aria-expanded", "true"); document.body.style.overflow = "hidden";
    focusables()[0]?.focus();
  };
  opener.addEventListener("click", open);
  menu.querySelector("[data-menu-close]")?.addEventListener("click", () => close());
  menu.querySelectorAll("[data-menu-link]").forEach((a) => a.addEventListener("click", () => close(false)));
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
    if (e.key === "Tab") {
      const f = focusables(); const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  matchMedia("(min-width: 761px)").addEventListener("change", (e) => { if (e.matches && !menu.hidden) close(false); });
}

// Einblenden beim Scrollen. Robust gegen schnelles Scrollen und Anker-Sprünge: alles, was oberhalb der
// Fensterunterkante liegt (auch bereits übersprungene Elemente), wird sichtbar.
const pending = new Set(document.querySelectorAll<HTMLElement>(".reveal"));
if (reduced.matches) pending.forEach((el) => el.classList.add("is-in"));
else {
  let queued = false;
  const check = () => {
    queued = false;
    const limit = innerHeight * 0.95;
    for (const el of pending) if (el.getBoundingClientRect().top < limit) { el.classList.add("is-in"); pending.delete(el); }
    if (!pending.size) { removeEventListener("scroll", onScroll); removeEventListener("resize", onScroll); }
  };
  const onScroll = () => { if (!queued) { queued = true; requestAnimationFrame(check); } };
  check();
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll, { passive: true });
  addEventListener("hashchange", onScroll);
  setTimeout(check, 400); // nach Sprung zu #anker beim Laden
}

// Hero-Orb: echte NuOrb-Animation, als Vorführung durch die Zustände; reagiert auf den Zeiger. Kein Mikrofon.
const heroOrb = document.querySelector<HTMLElement>("[data-hero-orb]");
const stateLabel = document.querySelector<HTMLElement>("[data-orb-state]");
if (heroOrb) {
  const labels: Record<string, string> = JSON.parse(stateLabel?.dataset.labels || "{}");
  const seq: [string, number][] = [["idle", 3600], ["listening", 3200], ["thinking", 2400], ["speaking", 4200]];
  let i = 0, timer = 0, visible = true, pointer = 0, speakT = 0, raf = 0;
  const orb = () => window.Orb;
  const cssOrb = heroOrb.querySelector<HTMLElement>(".orb-css");
  const setState = (s: string) => {
    heroOrb.dataset.state = s;
    orb()?.set({ state: s });
    if (stateLabel) stateLabel.textContent = labels[s] || s;
  };
  const step = () => {
    if (!visible || reduced.matches) return;
    const [s, ms] = seq[i % seq.length]; i++;
    setState(s); timer = window.setTimeout(step, ms);
  };
  // Pegel: Zeigernähe + simuliertes Sprechen (rein visuell)
  const tick = (t: number) => {
    raf = requestAnimationFrame(tick);
    if (!visible) return;
    const s = heroOrb.dataset.state;
    let lvl = pointer * 0.45;
    if (s === "speaking") { speakT = t / 1000; lvl = Math.max(lvl, 0.35 + 0.3 * Math.abs(Math.sin(speakT * 7.3) * Math.sin(speakT * 2.1 + 1))); }
    else if (s === "listening") lvl = Math.max(lvl, 0.15 + 0.1 * Math.abs(Math.sin(t / 380)));
    const o = orb();
    if (o) o.set({ level: lvl }); else cssOrb?.style.setProperty("--lvl", lvl.toFixed(3)); // CSS-Orb reagiert ebenfalls
  };
  heroOrb.closest(".hero")?.addEventListener("pointermove", (e) => {
    const r = heroOrb.getBoundingClientRect();
    const pe = e as PointerEvent;
    const dx = (pe.clientX - (r.left + r.width / 2)) / r.width, dy = (pe.clientY - (r.top + r.height / 2)) / r.height;
    pointer = Math.max(0, 1 - Math.hypot(dx, dy) * 1.6);
  });
  heroOrb.closest(".hero")?.addEventListener("pointerleave", () => { pointer = 0; });
  const start = () => {
    orb()?.calm(reduced.matches);
    if (reduced.matches) { setState("idle"); return; }
    clearTimeout(timer); step();
    cancelAnimationFrame(raf); raf = requestAnimationFrame(tick);
  };
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    orb()?.calm(!visible || reduced.matches);
    if (visible) start(); else { clearTimeout(timer); cancelAnimationFrame(raf); }
  }).observe(heroOrb);
  reduced.addEventListener("change", start);

  // orb.js erst nach dem Laden nachladen (nicht auf dem kritischen Pfad). Ohne GPU-Beschleunigung (Software-WebGL wie
  // SwiftShader/llvmpipe) bleibt der CSS-Orb – derselbe Fallback wie im Produkt, aber ohne den Hauptthread zu blockieren.
  // ?orb=webgl erzwingt den WebGL-Orb (Tests), ?orb=css den CSS-Orb.
  const softwareGL = () => {
    try {
      const gl = document.createElement("canvas").getContext("webgl", { failIfMajorPerformanceCaveat: true }) as WebGLRenderingContext | null;
      if (!gl) return true;
      const ext = gl.getExtension("WEBGL_debug_renderer_info");
      const name = String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
      gl.getExtension("WEBGL_lose_context")?.loseContext();
      return /swiftshader|llvmpipe|softpipe|software|basic render/i.test(name);
    } catch { return true; }
  };
  const loadOrb = () => {
    const force = new URLSearchParams(location.search).get("orb");
    if (force === "css" || (force !== "webgl" && softwareGL())) { heroOrb.dataset.renderer = "css"; return; }
    const sc = document.createElement("script");
    sc.src = "/orb/orb.js";
    sc.onload = () => { heroOrb.dataset.renderer = window.Orb?.renderer || "?"; setState(heroOrb.dataset.state || "idle"); orb()?.calm(!visible || reduced.matches); };
    document.body.append(sc);
  };
  const idle = (fn: () => void) => ("requestIdleCallback" in window ? (window as Window & { requestIdleCallback: (f: () => void, o?: object) => void }).requestIdleCallback(fn, { timeout: 1500 }) : setTimeout(fn, 300));
  if (document.readyState === "complete") idle(loadOrb); else addEventListener("load", () => idle(loadOrb), { once: true });
}

// Video-Poster erst kurz vor dem Sichtbarwerden laden (Seite startet schneller)
const setPoster = (v: HTMLVideoElement) => { if (v.dataset.lazyPoster) v.poster = v.dataset.lazyPoster; delete v.dataset.lazyPoster; };
const pio = "IntersectionObserver" in window
  ? new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { setPoster(e.target as HTMLVideoElement); pio?.unobserve(e.target); } }), { rootMargin: "800px 0px" })
  : null;
const lazyPoster = (v: HTMLVideoElement, url?: string) => {
  if (url) v.dataset.lazyPoster = url;
  if (pio) pio.observe(v); else setPoster(v);
};
document.querySelectorAll<HTMLVideoElement>("video[data-lazy-poster]").forEach((v) => lazyPoster(v));

// Kopieren des Installationsbefehls (nur Zwischenablage, nichts wird ausgeführt)
document.querySelectorAll<HTMLButtonElement>("[data-copy]").forEach((b) => {
  if (!navigator.clipboard) return;
  b.hidden = false;
  const label = b.querySelector("span")!;
  const orig = label.textContent;
  b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy!); label.textContent = b.dataset.copied || "✓"; }
    catch { label.textContent = orig; return; }
    setTimeout(() => { label.textContent = orig; }, 2000);
  });
});

// Demo: Geräte-Tabs, Szenen, eigene Steuerung. Nur vorproduzierte Videos von diesem Server.
type V = { src: string; type: string; w: number; h: number };
type Clip = { id: string; loop: boolean; video: V[]; sound: V[]; poster: Record<string, string>; tracks: { src: string; srclang: string; label: string }[]; alt: string };
const demo = document.querySelector<HTMLElement>("[data-demo]");
if (demo) {
  const tabs = Array.from(demo.querySelectorAll<HTMLButtonElement>("[data-tab]"));
  const panels = Array.from(demo.querySelectorAll<HTMLElement>("[data-panel]"));
  const t: Record<string, string> = JSON.parse(demo.dataset.i18n || "{}");
  const canWebm = document.createElement("video").canPlayType('video/webm; codecs="vp9"') !== "";
  const pick = (vs: V[], cssW: number) => {
    const want = cssW * Math.min(devicePixelRatio || 1, 2);
    const ok = vs.filter((v) => (v.type.startsWith("video/webm") ? canWebm : true));
    const pref = ok.filter((v) => v.type.startsWith(canWebm ? "video/webm" : "video/mp4"));
    const list = (pref.length ? pref : ok).sort((a, b) => a.w - b.w);
    return list.find((v) => v.w >= want) ?? list[list.length - 1];
  };

  const players = panels.map((panel) => {
    const video = panel.querySelector<HTMLVideoElement>("[data-video]");
    const ctrl = panel.querySelector<HTMLElement>("[data-ctrl]");
    if (!video || !ctrl) return null;
    video.removeAttribute("controls");
    ctrl.hidden = false;
    const btn = (a: string) => ctrl.querySelector<HTMLButtonElement>(`[data-act="${a}"]`)!;
    const play = btn("play"), sound = btn("sound"), cc = btn("cc"), bar = ctrl.querySelector<HTMLElement>("[data-progress]")!;
    const desc = panel.querySelector<HTMLElement>("p[data-desc]");
    const scenes = Array.from(panel.querySelectorAll<HTMLButtonElement>("[data-scene]"));
    const reducedNote = panel.querySelector<HTMLElement>("[data-reduced]");
    let clip: Clip | null = null, withSound = false, userPaused = false, inView = false, ccTrack = -1;

    const pageLang = root.lang;
    // audible = es läuft Ton (Film ohne Loop oder eingeschaltete Ton-Fassung eines Loops)
    const load = (c: Clip, sound_ = false, autoplay = false) => {
      clip = c;
      withSound = !c.loop || (sound_ && c.sound.length > 0);
      const guess: Record<string, number> = { phone: 300, tablet: 700, desktop: 900 };
      const v = pick(c.loop && withSound ? c.sound : c.video, video.clientWidth || guess[panel.dataset.panel || ""] || 640);
      video.pause();
      video.replaceChildren();
      // Poster erst setzen, wenn das Panel sichtbar ist (versteckte Tabs laden nichts)
      const poster = c.poster.webp || c.poster.jpg || "";
      if (panel.hidden) video.dataset.poster = poster;
      else if (video.hasAttribute("data-lazy-poster")) video.dataset.lazyPoster = poster;
      else video.poster = poster;
      video.muted = !withSound; video.loop = !withSound;
      video.preload = withSound ? "metadata" : "none";
      video.setAttribute("aria-label", c.alt);
      if (v) video.src = v.src;
      const tracks = withSound ? c.tracks : [];
      // Untertitel in Seitensprache; automatisch an, wenn die Aufnahme eine andere Sprache spricht
      const showFor = tracks.find((tr) => tr.srclang === pageLang) ?? tracks[0];
      const autoOn = !!showFor && !c.id.endsWith("-" + pageLang);
      for (const tr of tracks) {
        const el = document.createElement("track");
        el.kind = "subtitles"; el.src = tr.src; el.srclang = tr.srclang; el.label = tr.label; el.default = autoOn && tr === showFor;
        video.append(el);
      }
      ccTrack = showFor ? tracks.indexOf(showFor) : -1;
      sound.hidden = !c.loop || c.sound.length === 0;
      sound.setAttribute("aria-pressed", String(c.loop && withSound));
      sound.setAttribute("aria-label", c.loop && withSound ? t.mute : t.sound);
      cc.hidden = tracks.length === 0;
      cc.setAttribute("aria-pressed", String(autoOn));
      bar.style.width = "0";
      if (autoplay) video.play().catch(() => {});
    };
    const sync = () => {
      const playing = !video.paused && !video.ended;
      ctrl.classList.toggle("is-playing", playing);
      play.setAttribute("aria-label", playing ? t.pause : t.play);
    };
    ["play", "pause", "ended"].forEach((ev) => video.addEventListener(ev, sync));
    video.addEventListener("timeupdate", () => { if (video.duration) bar.style.width = `${(video.currentTime / video.duration) * 100}%`; });
    play.addEventListener("click", () => {
      if (video.paused) { userPaused = false; video.play().catch(() => {}); } else { userPaused = true; video.pause(); }
    });
    btn("replay").addEventListener("click", () => { video.currentTime = 0; userPaused = false; video.play().catch(() => {}); });
    sound.addEventListener("click", () => { if (clip) { userPaused = false; load(clip, !withSound, true); } });
    cc.addEventListener("click", () => {
      const tt = video.textTracks[ccTrack]; if (!tt) return;
      const on = tt.mode !== "showing";
      for (const x of Array.from(video.textTracks)) x.mode = "hidden";
      tt.mode = on ? "showing" : "hidden"; cc.setAttribute("aria-pressed", String(on));
    });
    btn("fs").addEventListener("click", () => {
      const el = video as HTMLVideoElement & { webkitEnterFullscreen?: () => void };
      if (el.requestFullscreen) el.requestFullscreen().catch(() => {}); else el.webkitEnterFullscreen?.();
    });
    scenes.forEach((s) => s.addEventListener("click", () => {
      scenes.forEach((o) => o.setAttribute("aria-pressed", String(o === s)));
      const c = JSON.parse(s.dataset.scene!) as Clip;
      if (desc) desc.textContent = s.dataset.desc || desc.textContent;
      userPaused = false;
      load(c, false, true); // ausdrücklicher Klick = Abspielwunsch
    }));
    if (reduced.matches && reducedNote) reducedNote.hidden = false;
    const first = scenes[0] ? (JSON.parse(scenes[0].dataset.scene!) as Clip) : null;
    if (first) load(first);
    sync();
    const visibleAuto = () => {
      if (inView && !panel.hidden && !reduced.matches && !userPaused && !withSound) video.play().catch(() => {});
      else if (!inView || panel.hidden) video.pause();
    };
    new IntersectionObserver(([e]) => { inView = e.isIntersecting && e.intersectionRatio > 0.35; visibleAuto(); }, { threshold: [0, 0.35, 0.6] }).observe(video);
    return { panel, video, visibleAuto };
  });

  const select = (tab: HTMLButtonElement, focus = false) => {
    tabs.forEach((b) => { const on = b === tab; b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; });
    panels.forEach((p) => {
      p.hidden = p.dataset.panel !== tab.dataset.tab;
      const v = p.querySelector<HTMLVideoElement>("[data-video]");
      if (!p.hidden && v?.dataset.poster) { lazyPoster(v, v.dataset.poster); delete v.dataset.poster; }
    });
    players.forEach((p) => p?.visibleAuto());
    if (focus) tab.focus();
  };
  // Auf schmalen Bildschirmen mit der Smartphone-Ansicht beginnen (falls vorhanden)
  const phoneTab = tabs.find((b) => b.dataset.tab === "phone");
  if (phoneTab && matchMedia("(max-width: 600px)").matches && demo.querySelector('[data-panel="phone"] [data-scene]')) select(phoneTab);
  tabs.forEach((b, i) => {
    b.addEventListener("click", () => select(b));
    b.addEventListener("keydown", (e) => {
      const k = e.key; let n = -1;
      if (k === "ArrowRight") n = (i + 1) % tabs.length; else if (k === "ArrowLeft") n = (i - 1 + tabs.length) % tabs.length;
      else if (k === "Home") n = 0; else if (k === "End") n = tabs.length - 1;
      if (n >= 0) { e.preventDefault(); select(tabs[n], true); }
    });
  });
}

export {};
