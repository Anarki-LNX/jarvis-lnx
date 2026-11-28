// Browser-Prüfung der gebauten Website mit headless Chromium (DevTools-Protokoll, keine npm-Pakete).
// Prüft je Seite × Viewport: Konsolenfehler/Exceptions, CSP-Verstöße, Requests nur same-origin, kein horizontales
// Scrollen, Orb-Renderer, Mikrofon nie angefragt. Screenshots nach .tmp/audit/. Schonend: nice 19, ein Browser,
// eigenes Wegwerf-Profil, Prozessgruppe wird am Ende beendet, Zeitdeckel.
// Aufruf: node tools/audit.mjs [--full] [--reduced]
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { serve } from "./serve.mjs";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(web, ".tmp/audit");
mkdirSync(outDir, { recursive: true });
const full = process.argv.includes("--full");
const reducedRun = process.argv.includes("--reduced");
const PORT = 4499, CDP = 9400 + Math.floor(Math.random() * 300), ORIGIN = `http://127.0.0.1:${PORT}`;
const pages = ["/", "/en/", "/en/?orb=webgl", "/de/", "/en/privacy/", "/de/datenschutz/", "/does-not-exist"];
const viewports = [
  ["w1920", 1920, 1080, 1, false], ["w1440", 1440, 900, 1, false], ["w1024", 1024, 768, 2, true],
  ["w768", 768, 1024, 2, true], ["w430", 430, 932, 3, true], ["w390", 390, 844, 3, true], ["w360", 360, 740, 3, true],
  ["phone-l", 844, 390, 3, true],
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const killTimer = setTimeout(() => { console.error("Zeitdeckel erreicht"); cleanup(); process.exit(2); }, 8 * 60 * 1000);

const srv = await serve(PORT);
const prof = mkdtempSync(join(web, ".tmp/chrome-"));
const chrome = spawn("nice", ["-n", "19", "chromium", "--headless=new", "--no-first-run", "--no-default-browser-check", `--user-data-dir=${prof}`,
  `--remote-debugging-port=${CDP}`, "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--hide-scrollbars", "--mute-audio",
  "--autoplay-policy=no-user-gesture-required", "--renderer-process-limit=2", "about:blank"], { stdio: "ignore", detached: true });
function cleanup() {
  try { process.kill(-chrome.pid, "SIGTERM"); } catch {}
  setTimeout(() => { try { process.kill(-chrome.pid, "SIGKILL"); } catch {} rmSync(prof, { recursive: true, force: true }); }, 800);
  srv.close();
}

let ws, id = 0;
const pending = new Map(), events = [];
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
const problems = [], notes = [];
try {
  let target;
  for (let i = 0; i < 60 && !target; i++) {
    await sleep(250);
    try { target = (await (await fetch(`http://127.0.0.1:${CDP}/json/list`)).json()).find((t) => t.type === "page"); } catch {}
  }
  if (!target) throw new Error("Chromium nicht erreichbar");
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(d.error.message)) : p.res(d.result); return; }
    events.push(d);
  });
  await send("Runtime.enable"); await send("Log.enable"); await send("Network.enable"); await send("Page.enable");
  await send("Browser.setPermission", { permission: { name: "microphone" }, setting: "denied" }).catch(() => {});

  const vps = full ? viewports : viewports.filter((v) => ["w1440", "w768", "w390"].includes(v[0]));
  for (const [vname, w, h, dpr, mobile] of vps) {
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: dpr, mobile });
    await send("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: mobile ? 5 : 1 });
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: reducedRun ? "reduce" : "no-preference" }] });
    for (const page of pages) {
      if (!full && vname !== "w1440" && !["/en/", "/de/"].includes(page)) continue;
      if (page.includes("?orb=") && vname !== "w1440" && vname !== "w390") continue;
      events.length = 0;
      await send("Runtime.evaluate", { expression: "try{localStorage.clear()}catch(e){}" }).catch(() => {});
      await send("Page.navigate", { url: ORIGIN + page });
      await sleep(2200);
      // langsam durchscrollen, damit Reveal/Lazy-Load/Videos auslösen
      const r = await send("Runtime.evaluate", { returnByValue: true, awaitPromise: true, expression: `(async () => {
        const H = document.documentElement.scrollHeight; for (let y = 0; y < H; y += innerHeight * .8) { scrollTo({ top: y, behavior: "instant" }); await new Promise(r => setTimeout(r, 120)); }
        await new Promise(r => setTimeout(r, 400));
        const notRevealed = [...document.querySelectorAll(".reveal:not(.is-in)")].map(e => (e.closest("section")?.id || "?") + ">" + e.className).slice(0, 6);
        scrollTo(0, 0); await new Promise(r => setTimeout(r, 500));
        const sw = document.documentElement.scrollWidth, iw = innerWidth;
        const wide = sw > iw ? [...document.querySelectorAll("body *")].filter(e => { const b = e.getBoundingClientRect(); return b.right > iw + 1 && getComputedStyle(e).position !== "fixed"; }).slice(0, 5).map(e => e.tagName + "." + [...e.classList].join(".")) : [];
        const small = [...document.querySelectorAll("a, button, summary")].filter(e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && (b.height < 24 || b.width < 24) && getComputedStyle(e).visibility !== "hidden"; }).slice(0, 5).map(e => e.tagName + ":" + (e.textContent || "").trim().slice(0, 20));
        const imgsNoAlt = [...document.images].filter(i => !i.hasAttribute("alt")).length;
        const h1 = document.querySelectorAll("h1").length;
        const dupIds = (() => { const s = new Set(), d = []; document.querySelectorAll("[id]").forEach(e => { if (s.has(e.id)) d.push(e.id); s.add(e.id); }); return d; })();
        return { notRevealed, sw, iw, wide, small, imgsNoAlt, h1, dupIds, renderer: document.querySelector("[data-hero-orb]")?.dataset.renderer ?? null, lang: document.documentElement.lang, title: document.title, H: document.documentElement.scrollHeight };
      })()` });
      const v = r.result.value;
      const tag = `${vname} ${page}`;
      if (v.sw > v.iw) problems.push(`${tag}: horizontales Scrollen (${v.sw} > ${v.iw}) durch ${v.wide.join(", ")}`);
      if (v.notRevealed.length) problems.push(`${tag}: nach dem Durchscrollen unsichtbar: ${v.notRevealed.join(" | ")}`);
      if (v.imgsNoAlt) problems.push(`${tag}: ${v.imgsNoAlt} Bild(er) ohne alt`);
      if (v.h1 !== 1) problems.push(`${tag}: ${v.h1} h1-Elemente`);
      if (v.dupIds.length) problems.push(`${tag}: doppelte IDs ${v.dupIds.join(",")}`);
      if (v.small.length && mobile) notes.push(`${tag}: kleine Tippziele ${v.small.join(" | ")}`);
      if (page.startsWith("/en/") || page === "/de/") notes.push(`${tag}: Orb-Renderer ${v.renderer}, Höhe ${v.H}px`);
      for (const e of events) {
        if (e.method === "Runtime.exceptionThrown") problems.push(`${tag}: Exception ${e.params.exceptionDetails.exception?.description || e.params.exceptionDetails.text}`);
        if (e.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(e.params.type)) problems.push(`${tag}: console.${e.params.type} ${e.params.args.map((a) => a.value ?? a.description).join(" ")}`);
        if (e.method === "Log.entryAdded" && ["error", "warning"].includes(e.params.entry.level) && !(page === "/does-not-exist" && /404/.test(e.params.entry.text)))
          problems.push(`${tag}: ${e.params.entry.source} ${e.params.entry.level}: ${e.params.entry.text}${e.params.entry.url ? " " + e.params.entry.url : ""}`);
        if (e.method === "Network.requestWillBeSent") {
          const u = e.params.request.url;
          if (!u.startsWith(ORIGIN) && !u.startsWith("data:") && !u.startsWith("blob:")) problems.push(`${tag}: Fremd-Request ${u}`);
        }
        if (e.method === "Network.responseReceived" && e.params.response.status >= 400 && page !== "/does-not-exist") problems.push(`${tag}: HTTP ${e.params.response.status} ${e.params.response.url}`);
      }
      if (["/en/", "/de/"].includes(page) && ["w1440", "w390"].includes(vname) && !reducedRun) {
        const d = await send("Runtime.evaluate", { returnByValue: true, awaitPromise: true, expression: `(async () => {
          const wait = (ms) => new Promise(r => setTimeout(r, ms)); const res = {};
          document.getElementById("demo").scrollIntoView(); await wait(2500);
          const vid = () => document.querySelector("[data-panel]:not([hidden]) video");
          res.startTab = document.querySelector('[data-tab][aria-selected="true"]')?.dataset.tab;
          res.autoplay = vid() ? { t: +vid().currentTime.toFixed(2), err: vid().error?.code ?? null, src: vid().currentSrc.split("/").pop() } : null;
          document.querySelector('[data-tab="phone"]').click(); await wait(300);
          const sc = [...document.querySelectorAll('[data-panel="phone"] [data-scene]')]; res.phoneScenes = sc.length;
          if (sc[1]) { sc[1].click(); await wait(2500); res.phoneClick = { t: +vid().currentTime.toFixed(2), muted: vid().muted, err: vid().error?.code ?? null, tracks: vid().textTracks.length, src: vid().currentSrc.split("/").pop() }; vid().pause();
            const sb = document.querySelector('[data-panel="phone"] [data-act="sound"]');
            if (sb && !sb.hidden) { sb.click(); await wait(2000); res.sound = { t: +vid().currentTime.toFixed(2), muted: vid().muted, tracks: vid().textTracks.length, src: vid().currentSrc.split("/").pop() }; vid().pause(); } }
          document.querySelector('[data-tab="desktop"]').click(); scrollTo(0, 0); await wait(300);
          return res; })()` });
        const x = d.result.value;
        notes.push(`${vname} ${page}: Demo ${JSON.stringify(x)}`);
        if (x.autoplay && (x.autoplay.err || x.autoplay.t <= 0)) problems.push(`${vname} ${page}: Demo-Loop spielt nicht (${JSON.stringify(x.autoplay)})`);
        if (x.sound && (x.sound.muted || x.sound.t <= 0 || !x.sound.tracks)) problems.push(`${vname} ${page}: Ton-Fassung fehlerhaft (${JSON.stringify(x.sound)})`);
        if (x.phoneClick && (x.phoneClick.err || x.phoneClick.t <= 0)) problems.push(`${vname} ${page}: Szene startet nicht (${JSON.stringify(x.phoneClick)})`);
      }
      if (["/en/", "/de/"].includes(page) && ["w1440", "w390", "w360"].includes(vname)) {
        // Installation: drei Reiter, Tastatur, Kopierknöpfe, kein Überlauf; Bildschirmfoto je Reiter
        const ways = ["docker", "compose", "proxmox"];
        const lang = page.slice(1, 3);
        for (const w of ways) {
          const r = await send("Runtime.evaluate", { returnByValue: true, awaitPromise: true, expression: `(async () => {
            const wait = (ms) => new Promise(r => setTimeout(r, ms));
            const bar = document.querySelector("[data-ways] [role=tablist]"); const tab = bar.querySelector('[data-way="${w}"]');
            tab.click(); await wait(150);
            const sec = document.getElementById("install"); sec.scrollIntoView({ behavior: "instant" }); await wait(450);
            const vis = [...document.querySelectorAll("[data-way-panel]")].filter((p) => !p.hidden).map((p) => p.dataset.wayPanel);
            const panel = document.querySelector('[data-way-panel="${w}"]');
            const copies = [...panel.querySelectorAll("[data-copy]")].filter((b) => !b.hidden && b.offsetWidth > 0).length;
            const over = [...panel.querySelectorAll("*")].filter((e) => e.getBoundingClientRect().right > innerWidth + 1).map((e) => e.tagName + "." + e.className).slice(0, 3);
            const barOver = bar.scrollWidth > bar.clientWidth + 1;
            const rr = sec.getBoundingClientRect();
            return { vis, sel: bar.querySelector("[aria-selected=true]").dataset.way, copies, over, barOver, barShown: !bar.hidden, top: rr.top + scrollY, h: rr.height }; })()` });
          const x = r.result.value; notes.push(`${vname} ${page}: Install ${w} ${JSON.stringify({ ...x, top: undefined, h: undefined })}`);
          const want = { docker: 1, compose: 3, proxmox: 1 }[w];
          if (!x.barShown || x.vis.join() !== w || x.sel !== w || x.copies !== want || x.over.length || x.barOver) problems.push(`${vname} ${page}: Install-Reiter ${w} fehlerhaft ${JSON.stringify(x)}`);
          const shot = await send("Page.captureScreenshot", { format: "jpeg", quality: 75, captureBeyondViewport: true, clip: { x: 0, y: x.top, width: v.iw, height: Math.min(x.h, 6000), scale: dpr > 1 ? 1 / dpr : 0.7 } });
          writeFileSync(join(outDir, `install-${lang}-${vname}-${w}.jpg`), Buffer.from(shot.data, "base64"));
        }
        const k = await send("Runtime.evaluate", { returnByValue: true, awaitPromise: true, expression: `(async () => {
          const wait = (ms) => new Promise(r => setTimeout(r, ms)); const bar = document.querySelector("[data-ways] [role=tablist]");
          const t = bar.querySelector('[data-way="docker"]'); t.click(); t.focus();
          t.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })); await wait(80);
          const wrap = document.activeElement.dataset.way;
          document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true })); await wait(80);
          const home = document.activeElement.dataset.way;
          location.hash = "#install-compose"; await wait(150);
          const hash = bar.querySelector("[aria-selected=true]").dataset.way;
          history.replaceState(null, "", location.pathname); bar.querySelector('[data-way="docker"]').click(); scrollTo(0, 0);
          return { wrap, home, hash }; })()` });
        const y = k.result.value; notes.push(`${vname} ${page}: Install-Tastatur ${JSON.stringify(y)}`);
        if (y.wrap !== "proxmox" || y.home !== "docker" || y.hash !== "compose") problems.push(`${vname} ${page}: Install-Tastatur/Anker fehlerhaft ${JSON.stringify(y)}`);
      }
      if (page === "/en/" && vname === "w390") {
        const m = await send("Runtime.evaluate", { returnByValue: true, awaitPromise: true, expression: `(async () => {
          const wait = (ms) => new Promise(r => setTimeout(r, ms)); const b = document.querySelector("[data-menu-open]"), sh = document.querySelector("[data-menu]");
          b.click(); await wait(200);
          const open = !sh.hidden && b.getAttribute("aria-expanded") === "true" && sh.contains(document.activeElement);
          sh.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await wait(100);
          const closed = sh.hidden && document.activeElement === b;
          const t = document.querySelector('[role="tab"][aria-selected="true"]'); t.focus();
          t.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })); await wait(100);
          const moved = document.activeElement !== t && document.activeElement.getAttribute("aria-selected") === "true";
          return { open, closed, moved }; })()` });
        const x = m.result.value; notes.push(`${vname} ${page}: Menü/Tabs ${JSON.stringify(x)}`);
        if (!x.open || !x.closed || !x.moved) problems.push(`${vname} ${page}: Menü oder Tab-Tastatur fehlerhaft ${JSON.stringify(x)}`);
      }
      const shot = await send("Page.captureScreenshot", { format: "jpeg", quality: 70, captureBeyondViewport: true, clip: { x: 0, y: 0, width: v.iw, height: Math.min(v.H, 16000), scale: dpr > 1 ? 1 / dpr : 0.6 } });
      writeFileSync(join(outDir, `${vname}${page.replace(/[/?=]/g, "_") || "_root"}.jpg`), Buffer.from(shot.data, "base64"));
    }
  }
} catch (e) { problems.push("Abbruch: " + e.message); }
finally { clearTimeout(killTimer); cleanup(); }
console.log(notes.join("\n"));
if (problems.length) { console.error(`\n✗ ${problems.length} Problem(e):\n  ` + [...new Set(problems)].join("\n  ")); process.exitCode = 1; }
else console.log(`\n✓ Browser-Prüfung ohne Befund (${full ? "alle" : "Haupt"}-Viewports${reducedRun ? ", reduzierte Bewegung" : ""}). Screenshots: .tmp/audit/`);
