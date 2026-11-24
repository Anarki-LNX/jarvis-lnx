// Screenshots der NuOrb-Verwaltung (Desktop/Tablet) per headless Chromium + DevTools-Protokoll (Node >= 22).
// Aufruf: ADMIN_PW_FILE=<datei> HOME=<dir mit .pki/nssdb> node tools/shot.mjs <basis-url> <ausgabeordner> <breite>x<hoehe> <ansicht[:js]>...
// Das Passwort wird aus einer Datei gelesen (nie als Argument), Login per fetch im Seitenkontext.
import { spawn } from "node:child_process";
import { writeFileSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base, outDir, size, ...views] = process.argv.slice(2);
const [W, H] = size.split("x").map(Number);
const port = 9300 + Math.floor(Math.random() * 500);
const prof = mkdtempSync(join(tmpdir(), "jadmin-shot-"));
const chrome = spawn("chromium", ["--headless=new", "--no-first-run", `--user-data-dir=${prof}`, `--remote-debugging-port=${port}`,
  "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws, id = 0; const pending = new Map(); const logs = [];
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.value;
try {
  let target;
  for (let i = 0; i < 50 && !target; i++) { await sleep(200); try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page"); } catch { /* */ } }
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(d.error.message)) : p.res(d.result); }
    if (d.method === "Runtime.consoleAPICalled") logs.push(d.params.type + ": " + d.params.args.map((a) => a.value ?? a.description).join(" "));
    if (d.method === "Runtime.exceptionThrown") logs.push("EXCEPTION: " + (d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text));
  });
  await send("Runtime.enable"); await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: W < 1100 ? 2 : 1, mobile: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "dark" }] });
  await send("Page.navigate", { url: base + "/" }); await sleep(2500);
  if (views[0] === "login") { const s = await send("Page.captureScreenshot", { format: "png" }); writeFileSync(join(outDir, `login-${W}.png`), Buffer.from(s.data, "base64")); views.shift(); }
  const pw = readFileSync(process.env.ADMIN_PW_FILE, "utf8").trim();
  logs.push("login: " + await ev(`fetch("/api/auth/login",{method:"POST",headers:{"X-NUORB":"1","Content-Type":"application/json"},body:JSON.stringify({password:${JSON.stringify(pw)}})}).then(r=>r.status)`));
  await send("Page.navigate", { url: `${base}/?angemeldet` }); await sleep(3000);
  for (const v of views) {
    const [name, js] = v.split(/:(.*)/s);
    await ev(`location.hash = ${JSON.stringify(name)}; window.scrollTo(0, 0)`); await sleep(3500);
    if (js) { logs.push(name + " js: " + JSON.stringify(await ev(js))); await sleep(1500); }
    const s = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    writeFileSync(join(outDir, `${name}${js ? "-x" : ""}-${W}.png`), Buffer.from(s.data, "base64"));
  }
  console.log("ok"); if (logs.length) console.log(logs.join("\n"));
} finally { chrome.kill(); }
