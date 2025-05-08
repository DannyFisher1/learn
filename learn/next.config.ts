import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ['http://127.0.0.1:9000', 'http://localhost:9000', 'http://localhost:9000'],
  
  /* config options here */
};
module.exports = {
  // ... rest of the configuration.
  output: "standalone",
};


export default nextConfig;
