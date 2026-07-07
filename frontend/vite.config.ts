import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://localhost:8000";
const mlflowProxyTarget = process.env.MLFLOW_PROXY_TARGET || "http://mlflow:5000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api/docs": {
        target: apiProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/docs/, "/docs"),
      },
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/ws": {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
      },
      "/docs": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/redoc": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/openapi.json": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/mlflow": {
        target: mlflowProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/mlflow/, ""),
      },
    },
  },
});