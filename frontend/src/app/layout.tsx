import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vandal War Room",
  description: "Break it. Fix it. Prove it. Red finds the gap, Blue enforces the fix.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
