import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // /earncheck path works on any host
      { source: '/earncheck', destination: '/supplier/earncheck' },
    ];
  },
};

export default nextConfig;
