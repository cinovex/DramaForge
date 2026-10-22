import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Toonflow",
  description: "AI 创作工作台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
