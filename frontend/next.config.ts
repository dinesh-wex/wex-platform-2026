import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  output: "standalone",
  eslint: {
    // Pre-existing lint warnings should not block production builds.
    // Run `npm run lint` locally to fix incrementally.
    ignoreDuringBuilds: true,
  },
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
