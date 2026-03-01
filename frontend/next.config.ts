import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // /earncheck path works on any host
      { source: '/earncheck', destination: '/supplier/earncheck' },
      // Proxy all /api/* requests to the FastAPI backend
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

export default nextConfig;
