import type { Metadata } from "next";
import { Inter, Inter_Tight } from "next/font/google";
import "./globals.css";

const interTight = Inter_Tight({
  variable: "--font-inter-tight",
  subsets: ["latin"],
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "businessintelligence.ai",
  description: "KPI storytelling engine — anomaly detection, prescriptions, and narrative for business metrics.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${interTight.variable} ${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-ground text-ink">{children}</body>
    </html>
  );
}
