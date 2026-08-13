import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "京奥AI智能运营系统｜JAOS",
  description: "京奥电竞内部AI智能运营平台，覆盖知识、财务与项目管理。",
  icons: { icon: "/jingao-mark-transparent.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  interactiveWidget: "resizes-content",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
