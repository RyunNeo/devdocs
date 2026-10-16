import type { NextConfig } from "next";
import path from "node:path";

const backend = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const standalone = process.env.DEPLOY_STANDALONE === "1";
const config: NextConfig = {
  output: standalone ? "standalone" : undefined,
  outputFileTracingRoot: standalone ? path.resolve(__dirname, "../..") : undefined,
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  devIndicators: false,
  experimental: { proxyClientMaxBodySize: 10 * 1024 * 1024 + 64 * 1024, proxyTimeout: 120000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};
export default config;
