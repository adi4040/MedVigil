import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "MedVigil Clinical Audit",
  description: "Structured clinical documentation review powered by MedVigil.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
