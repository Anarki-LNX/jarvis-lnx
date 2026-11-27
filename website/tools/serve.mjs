// Minimaler statischer Server für Tests: liefert dist/ mit denselben Sicherheits-Headern wie der Produktiv-Caddy
// (deploy/Caddyfile). Aufruf: node tools/serve.mjs [port]  – bindet nur an 127.0.0.1.
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync, createReadStream } from "node:fs";
import { join, extname, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = resolve(here, "../dist");
export const HEADERS = JSON.parse(readFileSync(join(here, "../deploy/headers.json"), "utf8"));
// Lokal ohne TLS: "upgrade-insecure-requests" würde die eigenen Dateien auf https umbiegen.
HEADERS["Content-Security-Policy"] = HEADERS["Content-Security-Policy"].replace(/;\s*upgrade-insecure-requests/, "");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
  ".png": "image/png", ".webp": "image/webp", ".avif": "image/avif", ".jpg": "image/jpeg", ".woff2": "font/woff2", ".xml": "application/xml",
  ".txt": "text/plain; charset=utf-8", ".webmanifest": "application/manifest+json", ".mp4": "video/mp4", ".webm": "video/webm", ".vtt": "text/vtt; charset=utf-8", ".json": "application/json" };

export function serve(port = 4499) {
  const srv = createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let f = join(dist, p);
    if (!f.startsWith(dist)) { res.writeHead(400).end(); return; }
    if (existsSync(f) && statSync(f).isDirectory()) f = join(f, "index.html");
    let status = 200;
    if (!existsSync(f)) { f = join(dist, "404.html"); status = 404; }
    const size = statSync(f).size;
    const h = { ...HEADERS, "Content-Type": TYPES[extname(f)] || "application/octet-stream", "Accept-Ranges": "bytes" };
    const range = req.headers.range && /bytes=(\d*)-(\d*)/.exec(req.headers.range);
    if (range && status === 200) {
      const start = range[1] ? +range[1] : 0, end = range[2] ? Math.min(+range[2], size - 1) : size - 1;
      res.writeHead(206, { ...h, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1 });
      createReadStream(f, { start, end }).pipe(res); return;
    }
    res.writeHead(status, { ...h, "Content-Length": size });
    if (req.method === "HEAD") res.end(); else createReadStream(f).pipe(res);
  });
  return new Promise((r) => srv.listen(port, "127.0.0.1", () => r(srv)));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = +(process.argv[2] || 4499);
  await serve(port);
  console.log(`dist/ auf http://127.0.0.1:${port}/`);
}
