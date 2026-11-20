/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker the API is reachable as http://api:8000; on the host it is published on localhost:8180.
// Ports 5180/8180 avoid clashes with the other local projects (Nexora uses 5173/8000).
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8180";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
