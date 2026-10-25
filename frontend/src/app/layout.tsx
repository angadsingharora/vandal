import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";

// One face for everything; figures use its tabular numerals.
// One face for the whole console, per the mock: the machine's voice everywhere.
const mono = JetBrains_Mono({ variable: "--font-pmono", subsets: ["latin"], weight: ["400", "500", "700"] });

export const metadata: Metadata = {
  title: "Vandal",
  description: "Break it. Fix it. Prove it. Red finds the gap, Blue enforces the fix.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={mono.variable}>
      <body>{children}</body>
    </html>
  );
}
