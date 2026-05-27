import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "策略回测系统 | AI Trading Backtest",
  description: "基于 Freqtrade 的加密货币策略回测与 AI 策略迭代系统",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
}
