import type { NextConfig } from "next";
import path from "node:path";

const config: NextConfig = {
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  poweredByHeader: false,
  transpilePackages: ["@dataflow/api-client"],
};
export default config;
