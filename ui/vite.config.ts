import { defineConfig } from "vitest/config";

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    lib: { entry: "src/app.ts", formats: ["es"], fileName: () => "app.js" },
    rollupOptions: { output: { assetFileNames: "style.css" } },
  },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts"] },
});
