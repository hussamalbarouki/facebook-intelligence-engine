import type { Metadata } from "next";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import { ConflictProvider } from "@/lib/conflicts/context";
import { ThemeProvider } from "@/lib/theme-context";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

export const metadata: Metadata = {
  title: "شعبة المعلومات - عين النسر",
  description:
    "منصة الرصد والتحليل المعلوماتي التابعة لشعبة المعلومات ضمن منظومة عين النسر.",
  applicationName: "شعبة المعلومات - عين النسر",
  keywords: [
    "OSINT",
    "dashboard",
    "Iran",
    "Israel",
    "Russia",
    "Ukraine",
    "conflict monitor",
    "air raid alerts",
    "drone tracker",
  ],
  authors: [{ name: "منظومة عين النسر - شعبة المعلومات" }],
  icons: {
    icon: "/eagle-eye-icon.png",
    shortcut: "/eagle-eye-icon.png",
    apple: "/eagle-eye-logo.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // suppressHydrationWarning: THEME_INIT_SCRIPT sets data-theme / data-mode on <html> before React hydrates.
    <html lang="ar" suppressHydrationWarning>
      <head>
        {/* Theme flash prevention: apply the saved accent + mode before hydration. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Noto+Kufi+Arabic:wght@400;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="scanlines antialiased">
        <ThemeProvider>
          <ConflictProvider>
            {children}
          </ConflictProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
