import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";

import { Sidebar } from "@/components/shell/Sidebar";
import { StatusBar } from "@/components/shell/StatusBar";
import { loadStatus } from "@/lib/status";

import "./globals.css";

const ibmPlex = IBM_Plex_Sans({
  variable: "--font-ibm-plex",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "RepoPulse — Operator Dashboard",
  description:
    "AIOps operator console: SLOs, incidents, ranked recommendations, action history.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const status = await loadStatus();
  return (
    <html lang="en" className={ibmPlex.variable}>
      <body className="min-h-screen antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-[color:var(--color-primary)] focus:px-3 focus:py-2 focus:text-sm focus:text-white"
        >
          Skip to main content
        </a>
        <div className="grid h-screen grid-cols-[15rem_1fr] grid-rows-[3.5rem_1fr]">
          <div className="row-span-2 border-r border-[color:var(--color-border)]">
            <Sidebar />
          </div>
          <StatusBar
            version={status.version}
            agenticEnabled={status.agenticEnabled}
          />
          <main
            id="main"
            tabIndex={-1}
            className="overflow-y-auto bg-[color:var(--color-bg)] px-8 py-8"
          >
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
