import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    define: {
      "globalThis.__MPLADS_API_BASE__": JSON.stringify(env.VITE_API_BASE_URL?.trim() ?? ""),
    },
    server: {
      proxy: { "/api": "http://127.0.0.1:8000" },
    },
  };
});
