import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CDSS — Clinical Decision Support System",
  description:
    "Hybrid AI-powered clinical decision support for PHWs and specialist doctors. Real-time triage, risk assessment, and escalation.",
  keywords: ["clinical", "decision", "support", "AI", "triage", "healthcare"],
};

import { ThemeProvider } from "@/components/layout/ThemeProvider";

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#050b14" />
      </head>
      <body>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
