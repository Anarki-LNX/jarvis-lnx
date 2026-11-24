// Prueft die UI in WebKitGTK (Engine des Handy-Kiosks) ueber WebKitWebDriver und macht einen Screenshot.
// Aufruf (unter Xvfb): WebKitWebDriver --port=4455 & node tools/webkit-check.mjs <url> <out.png> [js-ausdruck]
// Hinweis: acceptInsecureCerts nur fuer diesen lokalen Rendertest; fuer http://127.0.0.1 irrelevant.
import { writeFileSync } from "node:fs";
const [url, out, expr = "return document.title"] = process.argv.slice(2);
const B = "http://127.0.0.1:4455", sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const j = async (m, p, body) => (await fetch(B + p, { method: m, headers: { "Content-Type": "application/json" }, body: body && JSON.stringify(body) })).json();
const s = await j("POST", "/session", { capabilities: { alwaysMatch: { acceptInsecureCerts: true,
  "webkitgtk:browserOptions": { binary: "/usr/lib/webkitgtk-6.0/MiniBrowser", args: ["--automation"] } } } });
const id = s.value.sessionId; if (!id) { console.log(JSON.stringify(s)); process.exit(1); }
try {
  await j("POST", `/session/${id}/window/rect`, { width: 432, height: 960 });
  await j("POST", `/session/${id}/url`, { url });
  await sleep(6000);
  const r = await j("POST", `/session/${id}/execute/sync`, { script: expr, args: [] });
  console.log(JSON.stringify(r.value));
  const shot = await j("GET", `/session/${id}/screenshot`);
  writeFileSync(out, Buffer.from(shot.value, "base64")); console.log("ok", out);
} finally { await j("DELETE", `/session/${id}`); }
