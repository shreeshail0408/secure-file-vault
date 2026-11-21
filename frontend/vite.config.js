import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Production build is served by Django: assets live under /static/ (STATIC_URL).
  // The dev server (npm run dev) keeps serving from /.
  base: command === "build" ? "/static/" : "/",
  server: { port: 5173, strictPort: true }, // must match FRONTEND_URL (CORS) in backend/.env
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
  },
}));
