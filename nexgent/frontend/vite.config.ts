import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const host = process.env.TAURI_DEV_HOST;

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const agentServerTarget =
    env.VITE_AGENT_SERVER_BASE_URL?.trim() || "http://192.168.0.18:2024";
  const ragServerTarget =
    env.VITE_RAG_SERVER_BASE_URL?.trim() || "http://127.0.0.1:8765";
  const serviceProxy = {
    "/agent-server": {
      target: agentServerTarget,
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/agent-server/, "")
    },
    "/rag-server": {
      target: ragServerTarget,
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/rag-server/, "")
    }
  };

  return {
    plugins: [react()],
    clearScreen: false,
    server: {
      host: host || "127.0.0.1",
      port: 5173,
      strictPort: true,
      hmr: host
        ? {
            protocol: "ws",
            host,
            port: 1421
          }
        : undefined,
      proxy: serviceProxy,
      watch: {
        ignored: ["**/src-tauri/**"]
      }
    },
    preview: {
      host: "127.0.0.1",
      port: 4173,
      strictPort: true,
      proxy: serviceProxy
    }
  };
});
