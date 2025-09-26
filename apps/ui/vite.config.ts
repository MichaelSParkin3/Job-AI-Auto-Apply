import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { configDefaults } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  root: path.resolve(__dirname),
  base: "/ui/",
  build: {
    outDir: "dist",
    emptyOutDir: false,
  },
  server: {
    port: 5173,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/setup-tests.ts",
    globals: true,
    css: true,
    exclude: [...configDefaults.exclude, "tests/e2e/**"],
  },
});
