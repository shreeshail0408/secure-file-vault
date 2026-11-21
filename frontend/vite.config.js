import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true }, // must match FRONTEND_URL (CORS) in backend/.env
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
  },
});
