// Ende-zu-Ende-Messung der Sprachkette wie im Browser: Audio -> /api/stt -> /api/ask -> SSE -> erster Satz -> /api/tts
// Aufruf: NODE_EXTRA_CA_CERTS=jarvis-ca.crt node tools/voice-e2e.mjs <audio.webm> [base-url]
import { readFileSync } from "node:fs";
const [file, base = `https://${process.env.JARVIS_HOST || "jarvis.local"}:8443`] = process.argv.slice(2);
const t0 = performance.now(), ms = () => Math.round(performance.now() - t0);
const fd = new FormData(); fd.append("audio", new Blob([readFileSync(file)], { type: "audio/webm" }), "frage.webm");
const stt = await (await fetch(base + "/api/stt", { method: "POST", body: fd })).json();
console.log(ms(), "STT:", JSON.stringify(stt.text));
const ask = await (await fetch(base + "/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: stt.text }) })).json();
console.log(ms(), "Run:", ask.run_id);
const r = await fetch(`${base}/api/runs/${ask.run_id}/events`);
const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "", full = "", firstAudio = null, done = false;
async function speak(s) { const a = await fetch(base + "/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: s }) }); const b = await a.arrayBuffer(); if (firstAudio === null) { firstAudio = ms(); console.log(firstAudio, "ERSTES AUDIO bereit:", JSON.stringify(s), b.byteLength, "Bytes"); } }
while (!done) {
  const { value, done: d } = await rd.read(); if (d) break; buf += dec.decode(value, { stream: true }); let i;
  while ((i = buf.indexOf("\n\n")) >= 0) { const blk = buf.slice(0, i); buf = buf.slice(i + 2);
    for (const l of blk.split("\n")) { if (!l.startsWith("data:")) continue; const e = JSON.parse(l.slice(5));
      if (e.event === "message.delta") { full += e.delta; const m = full.match(/^[\s\S]{18,}?[.!?](\s|$)/); if (m && firstAudio === null && !speak._p) speak._p = speak(m[0]); }
      else if (e.event !== "reasoning.available") console.log(ms(), e.event, (e.tool || "") + " " + (e.preview || e.error || "").toString().slice(0, 80));
      if (e.event === "run.completed") { full = e.output || full; done = true; }
      if (["run.failed", "run.cancelled"].includes(e.event)) done = true; } } }
if (speak._p) await speak._p; else if (full) await speak(full);
console.log(ms(), "Antwort:", JSON.stringify(full));
