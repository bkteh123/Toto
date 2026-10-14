import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API is reached through /api so the browser never needs CORS.
// The same prefix is proxied by nginx in the Docker setup.
const API = "http://127.0.0.1:8000"; // backend address for the dev proxy

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});
