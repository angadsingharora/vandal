import { ImageResponse } from "next/og";
import { SITE } from "@/lib/site";

// The card a link to the site shows when shared: the headline, the one-line what, and the name.
export const runtime = "edge";
export const alt = `${SITE.name}: ${SITE.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 80px",
          background: "#ffffff",
          color: "#16181d",
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 26 }}>
          <span style={{ fontWeight: 600 }}>{SITE.name}</span>
          <span style={{ color: "#959ca9", letterSpacing: 2, textTransform: "uppercase", fontSize: 20 }}>{SITE.tagline}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          <div style={{ fontSize: 72, fontWeight: 700, lineHeight: 1.04, letterSpacing: -2, maxWidth: 1000 }}>
            Your books can balance while the money goes to the wrong person.
          </div>
          <div style={{ fontSize: 28, color: "#5d6472", lineHeight: 1.35, maxWidth: 980 }}>
            Vandal checks every action an AI finance agent takes before money moves, and keeps attacking its own checks so they
            get stronger.
          </div>
        </div>
        <div style={{ display: "flex", gap: 56 }}>
          {[
            ["$300,787 → $0", "exposure, before and after"],
            ["100% → 0%", "attack success on unseen variants"],
            ["80 of 80", "legitimate invoices still paid"],
          ].map(([n, l]) => (
            <div key={n} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 30, fontWeight: 600, color: "#16181d" }}>{n}</span>
              <span style={{ fontSize: 20, color: "#5d6472" }}>{l}</span>
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
