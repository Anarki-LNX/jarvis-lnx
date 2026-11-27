# NuOrb website

Source of the official NuOrb website, **https://nuorb.loopout.tech** – bilingual (English `/en/`, German `/de/`),
static, no cookies, no tracking, no third-party requests and **no live AI connection**. The demo shows prerecorded
videos only.

## Stack
- [Astro](https://astro.build) 7 (static output) + `@astrojs/sitemap`, TypeScript, hand-written CSS design system.
- No client-side framework. One small script (`src/scripts/site.ts`) for navigation, the hero orb, the demo player and
  the copy button.
- The hero uses the **real NuOrb orb** (`ui/static/orb.js` + `orb.css`, WebGL → Canvas 2D → CSS fallback), copied at
  build time by `scripts/prepare-assets.mjs`.

## Build
```bash
npm ci
npm run build        # prepare assets → astro build → scripts/check.mjs
npm run typecheck    # astro check
node tools/audit.mjs # headless Chromium: console, CSP, requests, layout in several viewports (--full for 7 viewports)
```
`scripts/check.mjs` fails the build on: private IP addresses (except the example `192.168.1.50`), e-mail addresses,
keys/tokens, local paths, the project's former name, missing i18n keys, external resources, broken internal links or
anchors, inline scripts/styles (CSP), microphone/camera or live-connection APIs, invalid PayPal links, and security
headers that differ between `deploy/headers.json` and `deploy/Caddyfile`.

### Media
Demo videos, posters, subtitles and screenshots are not stored in Git. `prepare-assets.mjs` reads them from
`NUORB_MEDIA_DIR` (a folder with `media-manifest.json`) and copies only the referenced files to `public/media/`.
Without media the site still builds; the demo then shows a notice and a link to the trailer on YouTube.
YouTube videos are only **linked**, never embedded.

### Offline build
`NUORB_OFFLINE=1 npm run build` skips the build-time lookup of the latest GitHub release (the line is then omitted).

## Content
- Texts: `src/i18n/en.ts` and `src/i18n/de.ts` (same structure, checked at build time).
- Links and central values: `src/config.ts`. **`PAYPAL_URL` stays `null` until the project owner confirms the link**;
  while it is `null`, the PayPal button is shown disabled.
- Open Graph images: `npm run og` (renders `og/og.html` with headless Chromium).

## Deployment
Static container (`caddy:2.11-alpine` + `dist/`, read-only, no published ports) behind the existing reverse proxy
that terminates TLS. Files in `deploy/`:
- `Dockerfile`, `Caddyfile` (security headers incl. CSP, caching, 404), `headers.json`
- `docker-compose.vps.yml`, `ausrollen.sh` (build, check, transfer image, start; `--zurueck <tag>` to roll back)
- `outer-caddy-block.caddy` (one-time block for the outer proxy), `pruefe-live.sh` (checks after rollout)

## License
MIT, like the rest of the repository. Fonts: Inter, Space Grotesk, JetBrains Mono (SIL Open Font License, see
`ui/static/fonts/LICENSE-*`).
