import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("../..", import.meta.url));
export default defineConfig({
  server: {
    fs: {
      // src imports shared JSON/SVG from the repository root.
      allow: [repoRoot],
    },
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
        configure(proxy) {
          proxy.on("proxyReq", (proxyReq, request) => {
            proxyReq.setHeader(
              "X-Forwarded-Host",
              request.headers.host || "127.0.0.1:5173",
            );
          });
        },
      },
    },
  },
});
