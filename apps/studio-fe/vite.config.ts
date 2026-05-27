import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tauri exposes the host info through env. We use it to skip the dev-server
// host check when running inside Tauri, and to disable the file watcher's
// polling on platforms where it's slow.
const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1430,
    strictPort: true,
    host: host || false,
    hmr: host
      ? { protocol: "ws", host, port: 1431 }
      : undefined,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  envPrefix: ["VITE_", "TAURI_"],
});
