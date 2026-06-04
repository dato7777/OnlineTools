import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname),
  // Konva/react-konva are client-only; keep them out of the server bundle.
  serverExternalPackages: ["konva", "canvas"],
};

export default nextConfig;
