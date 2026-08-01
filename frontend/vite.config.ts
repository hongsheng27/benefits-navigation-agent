import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    // The navigator flow tests walk several chat turns, each waiting out the
    // simulated typing delay, so they land near the 5s default and go flaky
    // once suites run in parallel.
    testTimeout: 20000,
  },
});
