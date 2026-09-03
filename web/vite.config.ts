import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build the app under /app so FastAPI serves the SPA there; proxy /api to the
// Python service during dev.
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: { outDir: "dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:7616" } },
});
