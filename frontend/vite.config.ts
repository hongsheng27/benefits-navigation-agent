import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export default defineConfig({
  // 與後端共用 repo 根目錄 `.env`（含 VITE_API_BASE_URL），不要只讀 frontend/。
  envDir: repoRoot,
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
