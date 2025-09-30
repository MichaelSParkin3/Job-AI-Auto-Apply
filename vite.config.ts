import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  resolve: {
    alias: {
      '/src': path.resolve(__dirname, 'apps/ui/src')
    }
  },
  build: {
    outDir: "apps/ui/dist",
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, "index.html"),
    },
  },
  server: {
    port: 5173,
  },
});