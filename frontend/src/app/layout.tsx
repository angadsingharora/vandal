import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vandal War Room",
  description: "Vandal Strike finds the gap in an AI finance agent's controls; Vandal Guard enforces the fix.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
