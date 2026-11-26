/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// In Docker the backend is reachable as http://backend:8000; on the host it is published on localhost:8180.
// Ports 5180/8180 avoid clashes with the other local projects (Nexora uses 5173/8000).
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8180";

export default defineConfig({
  plugins: [
    react(),
    // MP08 (G5): a web app manifest and a service worker that caches the app shell, so the salesman app opens with no
    // network. API calls are never cached by the service worker: offline data lives in IndexedDB (src/sales/db.ts).
    // The worker is registered by the production build (hosted demo), not by the dev server.
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "auto",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "AaharOS (DEMO)",
        short_name: "AaharOS",
        description: "Every gram traced. Every rupee explained. DEMO snack factory.",
        start_url: "/sales",
        scope: "/",
        display: "standalone",
        background_color: "#faf8f4",
        theme_color: "#b86e00",
        icons: [{ src: "/favicon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg}"],
        // Pages come from the network while online, so the server's current headers (its CSP) always apply; the cached
        // shell is only the offline fallback. (Serving the precached page first kept a stale CSP after a settings change.)
        navigateFallback: null,
        runtimeCaching: [
          {
            urlPattern: ({ request, url }) =>
              request.mode === "navigate" && !url.pathname.startsWith("/api/"),
            handler: "NetworkFirst",
            options: {
              cacheName: "pages",
              networkTimeoutSeconds: 5,
              precacheFallback: { fallbackURL: "/index.html" },
            },
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
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
