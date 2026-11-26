// Bereitet Assets für den Build vor – ohne Kopien im Git:
//  - Orb (echte Produkt-Animation) aus ../ui/static/orb.{js,css}
//  - Schriften + Lizenzen aus ../ui/static/fonts
//  - Screenshots aus NUORB_MEDIA_DIR/screenshots (aktuelle Oberfläche; die Repo-Bilder in docs/screenshots zeigen noch den alten Namen)
//  - Demo-Videos aus NUORB_MEDIA_DIR (Standard: ../../Xiaomi/marketing/website/media) → public/media + src/data/media.json
// Fehlende Medien brechen den Build nicht ab; die Demo zeigt dann einen ehrlichen Hinweis statt eines Videos.
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const repo = resolve(web, "..");
const pub = join(web, "public");
const log = (...a) => console.log("[assets]", ...a);

// 1) Orb
mkdirSync(join(pub, "orb"), { recursive: true });
// Kommentare werden entfernt (sie enthalten interne Projekt-Bezeichner); der Code bleibt unverändert.
for (const f of ["orb.js", "orb.css"]) {
  let src = readFileSync(join(repo, "ui/static", f), "utf8");
  src = src.replace(/\/\*[\s\S]*?\*\//g, "");                  // Blockkommentare (orb.js/orb.css enthalten keine "/*" in Strings)
  if (f.endsWith(".js")) src = src.replace(/^[ \t]*\/\/.*\n/gm, ""); // reine Zeilenkommentare (auch GLSL)
  src = src.replace(/^\s*\n/, "");
  writeFileSync(join(pub, "orb", f), `/* NuOrb orb – ui/static/${f} from https://github.com/Anarki-LNX/nuorb (MIT) */\n` + src);
}
log("orb.js/orb.css aus ui/static übernommen");

// 2) Schriften
mkdirSync(join(pub, "fonts"), { recursive: true });
for (const f of readdirSync(join(repo, "ui/static/fonts"))) cpSync(join(repo, "ui/static/fonts", f), join(pub, "fonts", f));
log("Schriften übernommen");

// 4) Demo-Medien aus dem Manifest der Video-Sitzung. Normalisiert auf:
//    { id, device, lang, title{en,de}, desc{en,de}, alt{en,de}, duration, loop, video[], sound[], poster{avif,webp,jpg}, tracks[] }
//    loop=true: stummer Loop (darf automatisch laufen); sound[] = optionale Fassung mit Ton (nur auf Klick).
//    loop=false: Film mit Ton (startet nie von selbst).
const mediaDir = resolve(process.env.NUORB_MEDIA_DIR || join(repo, "../Xiaomi/marketing/website/media"));
const manifestPath = join(mediaDir, "media-manifest.json");
mkdirSync(join(web, "src/data"), { recursive: true });
const okPath = (f) => typeof f === "string" && !f.includes("..") && !/^\w+:/.test(f) && !f.startsWith("/") && !f.startsWith("_build") && existsSync(join(mediaDir, f));
const need = new Set();
const use = (f) => { need.add(f); return "/media/" + f; };
let clips = [];

const HOLD = new Set(["desktop-setup-en", "install-tutorial-en"]);

function fromClipsFormat(list) {
  // Varianten (Größen) je Szene zusammenfassen; "-sound"-Szenen an den stummen Loop hängen.
  const groups = new Map();
  for (const c of list) {
    if (!["desktop", "tablet", "phone"].includes(c.device)) continue;
    // Social-Kurzfilme (eingeblendete Überschriften, YouTube-End-Karte) gehören nicht auf die Website
    if (String(c.clip || c.id).startsWith("phone-short-")) continue;
    // Vorerst zurückgehalten: zeigen die in v0.6.3 entfernte Stimme „Alan“ im Einrichtungsassistenten. Die Video-Sitzung
    // nimmt sie mit Joe unter gleichem Namen neu auf → dann hier austragen.
    if (HOLD.has(String(c.clip || c.id))) { log("zurückgehalten:", c.id); continue; }
    const files = [...(c.sources || []).map((x) => x.src), ...Object.values(c.poster || {}), ...(c.tracks || []).map((x) => x.src)];
    if (!c.sources?.length || files.some((f) => !okPath(f))) { log("übersprungen (Datei fehlt oder ungültiger Pfad):", c.id); continue; }
    const key = String(c.clip || c.id.replace(/-\d+$/, ""));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const out = new Map();
  const srcs = (vs) => vs.flatMap((v) => v.sources.map((x) => ({ src: use(x.src), type: x.type, w: v.width, h: v.height })));
  for (const [rawKey, vars] of groups) {
    const key = rawKey.replace(/-sound$/, "");
    const loops = vars.filter((v) => v.loop === true && !v.audio), withAudio = vars.filter((v) => v.audio);
    const main = loops.length ? loops : withAudio;
    if (!main.length) continue;
    const v0 = main[0];
    const target = v0.device === "phone" ? 720 : 1280;
    const pv = [...main].sort((a, b) => Math.abs(a.width - target) - Math.abs(b.width - target))[0];
    const tv = withAudio.length ? [...withAudio].sort((a, b) => Math.abs(a.width - target) - Math.abs(b.width - target))[0] : null;
    const prev = out.get(key);
    const clip = prev || { id: key, device: v0.device, lang: v0.lang, title: { en: v0.title_en, de: v0.title_de }, desc: { en: v0.caption_en, de: v0.caption_de },
      alt: { en: v0.alt_en, de: v0.alt_de }, duration: Math.round(v0.duration || 0), loop: loops.length > 0, video: [], sound: [],
      poster: Object.fromEntries(Object.entries(pv.poster || {}).map(([k, f]) => [k, use(f)])), tracks: [] };
    if (loops.length) { clip.loop = true; clip.video = srcs(loops); if (withAudio.length) clip.sound = srcs(withAudio); }
    else if (prev?.loop) clip.sound = srcs(withAudio);           // eigene "-sound"-Gruppe zum vorhandenen Loop
    else clip.video = srcs(withAudio);
    if (tv?.tracks?.length) clip.tracks = tv.tracks.map((x) => ({ src: use(x.src), srclang: x.srclang, label: x.label }));
    out.set(key, clip);
  }
  return [...out.values()];
}

function fromItemsFormat(list) {
  // ältere Form (manifest.py): items[] mit video[]/video_with_sound[]/poster[]/subtitles[] und Feld "path"
  const ok = (a) => (Array.isArray(a) ? a : []).filter((e) => e && okPath(e.path));
  return list.filter((it) => ["scene-loop", "long-video-with-sound"].includes(it.kind) && ["desktop", "tablet", "phone"].includes(it.device)).flatMap((it) => {
    const video = ok(it.video), sound = ok(it.video_with_sound), poster = ok(it.poster), subs = ok(it.subtitles);
    if (!video.length) return [];
    const v = (e) => ({ src: use(e.path), type: e.type, w: e.width, h: e.height });
    const loop = it.kind === "scene-loop";
    const head = (s) => (s || "").split(/[:(]/)[0].trim();
    return [{ id: String(it.id), device: it.device, lang: it.language, title: { en: head(it.description?.en), de: head(it.description?.de) }, desc: it.description || {},
      alt: it.alt || {}, duration: Math.round(Math.max(0, ...video.map((e) => e.duration || 0))), loop, video: video.map(v), sound: sound.map(v),
      poster: Object.fromEntries(poster.map((e) => [e.path.split(".").pop(), use(e.path)])), tracks: subs.map((e) => ({ src: use(e.path), srclang: e.srclang, label: e.label })) }];
  });
}

if (existsSync(manifestPath)) {
  const m = JSON.parse(readFileSync(manifestPath, "utf8"));
  clips = Array.isArray(m.clips) ? fromClipsFormat(m.clips) : Array.isArray(m.items) ? fromItemsFormat(m.items) : [];
  for (const f of need) {
    const dst = join(pub, "media", f);
    mkdirSync(dirname(dst), { recursive: true });
    if (!existsSync(dst) || statSync(dst).size !== statSync(join(mediaDir, f)).size) cpSync(join(mediaDir, f), dst);
  }
  log(`${clips.length} Szenen aus ${relative(repo, mediaDir) || mediaDir} übernommen (${need.size} Dateien)`);
} else log("kein media-manifest.json gefunden – Demo ohne Videos:", mediaDir);
// 5) Screenshots: <id>-<lang>[-<breite>].{avif,webp,jpg}; je Sprache die kleinste Variante mit Mindestbreite.
const SHOTS = { "app-conversation": 540, "app-orb-listening": 540, "app-confirmation-card": 540, "app-brain-switch": 540,
  "admin-model-fallback": 1280, "admin-overview": 1280, "admin-smart-home": 1280, "setup-llm-server": 1280, "pair-qr": 1280 };
const shots = {};
const shotDir = join(mediaDir, "screenshots");
const dims = (f) => {
  const r = spawnSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", f], { encoding: "utf8" });
  const [w, h] = (r.stdout || "").trim().split(",").map(Number); return w && h ? { w, h } : null;
};
if (existsSync(shotDir)) {
  const all = readdirSync(shotDir);
  for (const [id, minW] of Object.entries(SHOTS)) for (const lang of ["en", "de"]) {
    const re = new RegExp(`^${id}-${lang}(?:-(\\d+))?\\.jpg$`);
    const cands = all.map((f) => ({ f, m: re.exec(f) })).filter((x) => x.m)
      .map((x) => ({ stem: x.f.replace(/\.jpg$/, ""), d: dims(join(shotDir, x.f)) })).filter((x) => x.d).sort((a, b) => a.d.w - b.d.w);
    const pickd = cands.find((x) => x.d.w >= minW) || cands.at(-1);
    if (!pickd) continue;
    const entry = { w: pickd.d.w, h: pickd.d.h };
    for (const ext of ["avif", "webp", "jpg"]) if (existsSync(join(shotDir, `${pickd.stem}.${ext}`))) entry[ext] = use(`screenshots/${pickd.stem}.${ext}`);
    (shots[id] ||= {})[lang] = entry;
  }
  for (const f of need) if (f.startsWith("screenshots/")) { const dst = join(pub, "media", f); mkdirSync(dirname(dst), { recursive: true }); cpSync(join(mediaDir, f), dst); }
  log(`${Object.keys(shots).length} Screenshot-Motive übernommen`);
} else log("noch keine Screenshots im Medienordner – Feature-Karten ohne Bild");
writeFileSync(join(web, "src/data/media.json"), JSON.stringify({ clips, shots }, null, 1));
