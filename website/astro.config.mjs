// NuOrb website – static build (dist/). Languages live under /en/ and /de/; "/" is a neutral language picker.
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

const SITE = "https://nuorb.loopout.tech";

export default defineConfig({
  site: SITE,
  output: "static",
  trailingSlash: "ignore",
  build: { format: "directory", inlineStylesheets: "never", assets: "_assets" },
  compressHTML: true,
  integrations: [
    sitemap({
      filter: (page) => !/\/404/.test(page),
      // Sprachpaare explizit (die eingebaute i18n-Option hielte "/" für Englisch)
      serialize(item) {
        const pairs = [["/en/", "/de/"], ["/en/privacy/", "/de/datenschutz/"]];
        const path = new URL(item.url).pathname;
        const pair = pairs.find((p) => p.includes(path));
        if (pair) item.links = [{ lang: "en", url: SITE + pair[0] }, { lang: "de", url: SITE + pair[1] }, { lang: "x-default", url: SITE + "/" }];
        return item;
      },
    }),
  ],
  vite: { build: { assetsInlineLimit: 0 } },
});
