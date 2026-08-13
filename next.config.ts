import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The product only uses bundled brand assets. Keeping them unoptimized avoids
  // Cloudflare Images/ASSETS bindings in local NAS and Windows development,
  // where those managed bindings do not exist.
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
