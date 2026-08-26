import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "RazorBuy — Safe Agentic Commerce",
  description: "AI-native commerce with deterministic financial controls",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="flex h-screen bg-[#0f1117] text-[#e4e6f0] overflow-hidden antialiased">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-8 bg-[#0f1117]">{children}</main>
      </body>
    </html>
  );
}