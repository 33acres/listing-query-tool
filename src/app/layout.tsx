import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Scenario Revenue Analyzer",
  description: "Lステップの集計データから売上貢献を分析します",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
