import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Google広告 検索語句 自動診断ツール",
  description: "Google広告の検索語句レポートCSVを自動診断し、改善アクションを提示します",
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
