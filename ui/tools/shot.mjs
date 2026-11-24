// Screenshots der JARVIS-UI in Handy-Emulation (Mi 11 Lite: 412x915 CSS-px, DPR 2.625, Touch).
// Nutzt headless Chromium ueber das DevTools-Protokoll, keine npm-Pakete noetig (Node >= 22).
// Aufruf: node tools/shot.mjs <url> <ausgabe.png> [wartezeit_ms] [js-vor-screenshot]
// Zertifikat: Chromium vertraut der Heim-CA ueber eine eigene NSS-DB (HOME=<dir mit .pki/nssdb>).
import { spawn } from "node:child_process";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, out, waitMs = "2500", js = ""] = process.argv.slice(2);
const port = 9300 + Math.floor(Math.random() * 500);
const prof = mkdtempSync(join(tmpdir(), "jarvis-shot-"));
const chrome = spawn("chromium", ["--headless=new", "--no-first-run", `--user-data-dir=${prof}`, `--remote-debugging-port=${port}`,
  "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required", ...(process.env.CHROME_EXTRA || "").split(" ").filter(Boolean), "about:blank"],
  { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws, id = 0; const pending = new Map(); const logs = [];
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
try {
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    await sleep(200);
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page"); } catch (e) { /* noch nicht da */ }
  }
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(d.error.message)) : p.res(d.result); }
    if (d.method === "Runtime.consoleAPICalled") logs.push(d.params.type + ": " + d.params.args.map((a) => a.value ?? a.description).join(" "));
    if (d.method === "Runtime.exceptionThrown") logs.push("EXCEPTION: " + (d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text));
  });
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 412, height: 915, deviceScaleFactor: 2.625, mobile: true });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "dark" }] });
  await send("Page.enable");
  await send("Page.navigate", { url });
  await sleep(+waitMs);
  if (js) { const r = await send("Runtime.evaluate", { expression: js, awaitPromise: true, returnByValue: true }); if (r.result?.value !== undefined) logs.push("eval: " + JSON.stringify(r.result.value)); await sleep(1200); }
  const shot = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(out, Buffer.from(shot.data, "base64"));
  console.log("ok", out); if (logs.length) console.log(logs.join("\n"));
} finally { chrome.kill(); }
