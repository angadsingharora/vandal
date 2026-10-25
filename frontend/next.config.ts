import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // a second dev server (a preview beside the running demo) needs its own build dir
  distDir: process.env.NEXT_DIST_DIR || ".next",
  devIndicators: false, // the badge overlays bottom-left buttons on the demo screen
  agentRules: false, // don't write AGENTS.md into the repo on `next dev`
};

export default config;
