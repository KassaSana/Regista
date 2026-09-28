import { readFile } from "node:fs/promises";
import { resolve, sep } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// Exports are written by `uv run regista export` into the git-ignored out/exports.
const EXPORTS_DIRECTORY = resolve(import.meta.dirname, "../out/exports");

/**
 * Serve /exports/* from out/exports during development only.
 *
 * A build never copies an export, so StatsBomb-derived files cannot end up in
 * dist/ by accident (DATA_SOURCES.md).
 */
function localExports(): Plugin {
  return {
    name: "regista-local-exports",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/exports", async (request, response) => {
        const name = decodeURIComponent((request.url ?? "/").split("?")[0] ?? "/");
        const path = resolve(EXPORTS_DIRECTORY, `.${name}`);
        if (!path.startsWith(EXPORTS_DIRECTORY + sep) || !path.endsWith(".json")) {
          response.statusCode = 404;
          response.end();
          return;
        }
        try {
          const body = await readFile(path);
          response.setHeader("Content-Type", "application/json");
          response.setHeader("Cache-Control", "no-store");
          response.end(body);
        } catch {
          response.statusCode = 404;
          response.end();
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), localExports()],
  server: { port: 5173, strictPort: true },
});
