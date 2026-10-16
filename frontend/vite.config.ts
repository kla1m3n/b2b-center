/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // В режиме реального API запросы /api уходят на backend (uvicorn на 8000)
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    env: { VITE_USE_MOCKS: "true" }, // тесты не ходят в сеть — клиент API работает на заглушках
  },
});
