/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/app-weather-forecast/",
  plugins: [react()],
  build: {
    target: "es2020",
    // ECharts is a large but self-contained vendor chunk; it is split out
    // below so it caches independently. Raise the limit to keep output clean.
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          // Split the heavy charting library into its own chunk.
          echarts: ["echarts"],
          vendor: ["react", "react-dom", "@tanstack/react-query"],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
