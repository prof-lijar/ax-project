import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

const host = process.env.TAURI_DEV_HOST;
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.NEXGENT_BACKEND_TARGET || "http://127.0.0.1:8000";
  const proxy = Object.fromEntries(
    ["/api", "/auth", "/agent-server", "/weekly-report-bulk-api", "/scout-api", "/scout-scheduler-api", "/rag-api"]
      .map(prefix => [prefix, { target, proxyTimeout: 570_000 }])
  );
  return {
    plugins: [react()], clearScreen: false,
    test: { setupFiles: ["./src/testSetup.ts"] },
    server: { host: host || "127.0.0.1", port: 5173, strictPort: true,
      hmr: host ? { protocol: "ws", host, port: 1421 } : undefined,
      proxy, watch: { ignored: ["**/src-tauri/**"] } },
    preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy }
  };
});
