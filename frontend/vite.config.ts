import { defineConfig, type Plugin } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// The Python server reads only packaged files explicitly listed by this build.
// Do not expose arbitrary paths under the Python wheel as static resources.
function packagedAssetManifest(): Plugin {
  return {
    name: "packaged-asset-manifest",
    generateBundle(_options, bundle) {
      const allowed = ["index.html", ...Object.keys(bundle)].sort();
      this.emitFile({
        type: "asset",
        fileName: "asset-manifest.json",
        source: JSON.stringify(allowed),
      });
    },
  };
}

export default defineConfig(({mode})=>({
  base: "/web/",
  plugins: [svelte(), packagedAssetManifest()],
  build: {
    outDir: mode==="showcase"?"../dist/showcase/web":"../src/industrial_phm/apps/web_next",
    emptyOutDir: mode === "showcase",
    assetsDir: "assets",
    sourcemap: false,
  },
}));
