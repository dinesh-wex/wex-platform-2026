import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const rules: any[] = [
      // /earncheck path works on any host
      { source: '/earncheck', destination: '/supplier/earncheck' },
    ];
    // Proxy /api/* to FastAPI backend in local dev only.
    // In production, the load balancer handles routing.
    if (isDev) {
      rules.push({
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      });
    }
    return rules;
  },
};

export default nextConfig;
