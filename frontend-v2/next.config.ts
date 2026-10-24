import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  agentRules: false, // don't write AGENTS.md into the repo on `next dev`
};

export default config;
