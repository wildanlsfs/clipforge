import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// BACKEND_URL lets `npm run dev` point at a backend on a non-default port
// (e.g. when 8000 is already taken by something else on your machine):
//   BACKEND_URL=http://localhost:8010 npm run dev
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": BACKEND_URL,
    },
  },
});
