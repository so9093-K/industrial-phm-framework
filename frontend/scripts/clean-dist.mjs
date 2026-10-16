import { rmSync } from "node:fs";

const root = new URL("../../src/industrial_phm/apps/web_next/", import.meta.url);
for (const name of ["assets", "asset-manifest.json", "index.html"]) {
  rmSync(new URL(name, root), { recursive: true, force: true });
}
