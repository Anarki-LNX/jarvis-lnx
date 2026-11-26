// Prüfungen nach dem Build (dist/) und auf den Quellen. Bricht mit Exit 1 ab, wenn etwas nicht stimmt.
//  1. Datenschutz-Scan: private IPs (außer Beispiel 192.168.1.50), E-Mail-Adressen, Schlüssel/Tokens, lokale Pfade, alter Name
//  2. i18n: en.ts und de.ts haben exakt dieselbe Schlüsselstruktur (gleiche Array-Längen)
//  3. Keine externen Ressourcen: src/href von script/link/img/video/source/track nur same-origin
//  4. Interne Links und Anker existieren
//  5. Kein Mikrofon-/Kamera-Zugriff, keine Live-Verbindungen im ausgelieferten JS
//  6. PayPal-Links nur auf paypal.com / paypal.me
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, resolve, dirname, extname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(web, "dist");
const errors = [];
const err = (m) => errors.push(m);
const walk = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? walk(p) : [p]; });

if (!existsSync(dist)) { console.error("dist/ fehlt – erst bauen"); process.exit(1); }
const distFiles = walk(dist);
const textExt = new Set([".html", ".js", ".css", ".xml", ".txt", ".json", ".webmanifest", ".svg", ".vtt"]);
const srcFiles = [...walk(join(web, "src")), ...walk(join(web, "scripts")), ...walk(join(web, "og")), ...walk(join(web, "tools")), join(web, "README.md"), join(web, ".gitignore"), join(web, ".dockerignore"), ...["astro.config.mjs", "package.json"].map((f) => join(web, f))]
  .filter((f) => !f.includes("/data/media.json"));
const deployDir = join(web, "deploy");
if (existsSync(deployDir)) srcFiles.push(...walk(deployDir));

// 1) Datenschutz-Scan
const rules = [
  [/\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b/g, (m) => m !== "192.168.1.50", "private IP"],
  [/\b(?:100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\.\d{1,3}\.\d{1,3}\b/g, () => true, "Tailscale-IP"],
  [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, (m) => !/^(noreply|git)@/.test(m) && !/@\d/.test(m) && !/\.(png|webp|jpg|svg|woff2)$/.test(m), "E-Mail-Adresse"],
  [/\b(?:sk-ant-[\w-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|AKIA[0-9A-Z]{16}|xox[bap]-[\w-]{10,})/g, () => true, "Schlüssel/Token"],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/g, () => true, "privater Schlüssel"],
  [/\/home\/[a-z_][\w-]*/g, () => true, "lokaler Pfad"],
  [/\bnuorb\b/gi, () => true, "alter Name „NuOrb“"],
];
const scan = (file, text) => {
  for (const [re, keep, what] of rules) for (const m of text.match(re) || []) if (keep(m)) err(`Datenschutz: ${what} „${m}“ in ${relative(web, file)}`);
};
for (const f of distFiles) if (textExt.has(extname(f))) scan(f, readFileSync(f, "utf8"));
for (const f of srcFiles) if (/\.(astro|ts|mjs|js|css|html|json|sh|md|conf|yml|yaml)$|Caddyfile|Dockerfile/.test(f)) {
  // Quellen sind öffentlich – gleiche Regeln wie für dist/. Nur dieses Skript (enthält die Muster) ist ausgenommen.
  const text = readFileSync(f, "utf8");
  if (f.endsWith("scripts/check.mjs")) continue;
  scan(f, text);
}

// 2) i18n-Parität (Struktur der beiden Wörterbücher über die gebaute Ausgabe ist nicht prüfbar → Quellen per Node-Typstripping)
try {
  const en = (await import(join(web, "src/i18n/en.ts"))).default;
  const de = (await import(join(web, "src/i18n/de.ts"))).default;
  const shape = (o, p = "") => typeof o !== "object" || o === null ? [p + ":" + typeof o]
    : Array.isArray(o) ? [p + "[" + o.length + "]", ...o.flatMap((v, i) => shape(v, `${p}[${i}]`))]
    : Object.keys(o).sort().flatMap((k) => shape(o[k], p + "." + k));
  const a = new Set(shape(en)), b = new Set(shape(de));
  for (const k of a) if (!b.has(k)) err(`i18n: ${k} fehlt/abweichend in de.ts`);
  for (const k of b) if (!a.has(k)) err(`i18n: ${k} fehlt/abweichend in en.ts`);
} catch (e) { err("i18n: Wörterbücher nicht ladbar: " + e.message); }

// 3–6) HTML-Prüfungen
const htmlFiles = distFiles.filter((f) => f.endsWith(".html"));
const ids = new Map();
for (const f of htmlFiles) ids.set(f, new Set([...readFileSync(f, "utf8").matchAll(/\sid="([^"]+)"/g)].map((m) => m[1])));
const pageFor = (url) => {
  const p = url.split("#")[0].split("?")[0];
  if (!p.startsWith("/")) return null;
  const cand = [join(dist, p), join(dist, p, "index.html"), join(dist, p + ".html")];
  return cand.find((c) => existsSync(c) && statSync(c).isFile()) ?? null;
};
for (const f of htmlFiles) {
  const html = readFileSync(f, "utf8");
  const rel = relative(dist, f);
  for (const m of html.matchAll(/<(script|link|img|video|source|track|iframe|audio|embed|object)\b[^>]*?\s(?:src|href|poster|srcset)="([^"]+)"/gi)) {
    const [, tag, url] = m;
    if (tag.toLowerCase() === "link" && /rel="(canonical|alternate)"/.test(m[0])) continue;
    if (/^(https?:)?\/\//.test(url)) err(`Externe Ressource <${tag}> ${url} in ${rel}`);
    if (tag.toLowerCase() === "iframe") err(`iframe in ${rel}`);
  }
  for (const m of html.matchAll(/<a\b[^>]*\shref="([^"]+)"/gi)) {
    const url = m[1].replaceAll("&amp;", "&");
    if (url.startsWith("#")) { if (url.length > 1 && !ids.get(f).has(url.slice(1))) err(`Anker ${url} fehlt in ${rel}`); continue; }
    if (url.startsWith("/")) {
      const target = pageFor(url);
      if (!target) { err(`Interner Link ${url} ohne Ziel in ${rel}`); continue; }
      const hash = url.split("#")[1];
      if (hash && target.endsWith(".html") && !ids.get(target)?.has(hash)) err(`Anker ${url} fehlt (aus ${rel})`);
      continue;
    }
    if (/paypal/i.test(url) && !/^https:\/\/(www\.paypal\.com|(www\.)?paypal\.me)\/[\w\-./]+$/.test(url)) err(`Ungültiger PayPal-Link ${url} in ${rel}`);
    if (!/^(https:\/\/|mailto:)/.test(url)) err(`Unerwarteter Link ${url} in ${rel}`);
    if (/youtube\.com\/embed|youtube-nocookie/.test(url)) err(`YouTube-Einbettung in ${rel}`);
  }
  if (/\sstyle="/.test(html)) err(`Inline-style-Attribut in ${rel} (CSP style-src)`);
  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    if (/type="application\/ld\+json"/.test(m[1])) continue;
    if (m[2].trim()) err(`Inline-Skript in ${rel} (CSP script-src 'self')`);
  }
}
for (const f of distFiles.filter((x) => x.endsWith(".js"))) {
  const js = readFileSync(f, "utf8");
  for (const bad of ["getUserMedia", "mediaDevices", "WebSocket(", "EventSource(", "sendBeacon", "document.cookie", "eval(", "new Function("]) {
    if (js.includes(bad)) err(`Verbotene API ${bad} in ${relative(dist, f)}`);
  }
  for (const m of js.matchAll(/fetch\(\s*["'`]([^"'`]+)/g)) err(`fetch(${m[1]}) in ${relative(dist, f)}`);
}

// 6b) Externe Links: noopener; PayPal zusätzlich noreferrer
for (const f of htmlFiles) for (const m of readFileSync(f, "utf8").matchAll(/<a\b[^>]*href="https:\/\/[^"]*"[^>]*>/gi)) {
  if (!/rel="[^"]*noopener/.test(m[0])) err(`Externer Link ohne noopener in ${relative(dist, f)}: ${m[0].slice(0, 80)}`);
  if (/paypal/i.test(m[0]) && !/rel="[^"]*noreferrer/.test(m[0])) err(`PayPal-Link ohne noreferrer in ${relative(dist, f)}`);
}

// 6c) Lizenzhinweis der übernommenen Shader-Rauschfunktion (webgl-noise, MIT) muss in der ausgelieferten orb.js stehen
{ const orbJs = join(dist, "orb/orb.js");
  if (existsSync(orbJs)) { const o = readFileSync(orbJs, "utf8");
    if (/webgl-noise/.test(readFileSync(join(web, "../ui/static/orb.js"), "utf8")) && !(/webgl-noise/.test(o) && /Permission is hereby granted/.test(o))) err("orb/orb.js: Lizenzhinweis von webgl-noise fehlt"); } }

// 7) Caddyfile im Container setzt genau die Header aus deploy/headers.json (auch der lokale Testserver nutzt sie)
try {
  const hdr = JSON.parse(readFileSync(join(web, "deploy/headers.json"), "utf8"));
  const caddy = readFileSync(join(web, "deploy/Caddyfile"), "utf8");
  for (const [k, v] of Object.entries(hdr)) if (!caddy.includes(`${k} "${v}"`)) err(`deploy/Caddyfile: Header ${k} weicht von headers.json ab`);
} catch (e) { err("Header-Abgleich nicht möglich: " + e.message); }

if (errors.length) { console.error(`✗ ${errors.length} Problem(e):\n  ` + [...new Set(errors)].join("\n  ")); process.exit(1); }
console.log(`✓ Prüfungen bestanden: ${htmlFiles.length} Seiten, ${distFiles.length} Dateien, Datenschutz-Scan sauber, i18n gleich, keine externen Ressourcen.`);
