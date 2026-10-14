import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

export default defineConfig({
  base: "/abikan/",
  plugins: [react(), basicSsl()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/openmrs/abikan-api": {
        target: "http://127.0.0.1:8787",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/openmrs\/abikan-api/, ""),
      },
      "/openmrs": {
        target: "https://localhost",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
