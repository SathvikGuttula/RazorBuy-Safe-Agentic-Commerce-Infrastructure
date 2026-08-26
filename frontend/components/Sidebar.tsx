"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  ShoppingCart,
  Shield,
  ScrollText,
  Zap,
} from "lucide-react";

const nav = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/chat", label: "AI Chat", icon: MessageSquare },
  { href: "/orders", label: "Orders", icon: ShoppingCart },
  { href: "/policies", label: "Policies", icon: Shield },
  { href: "/audit", label: "Audit Log", icon: ScrollText },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-[#2e3345] bg-[#1a1d27] flex flex-col h-full flex-shrink-0">
      {/* Brand */}
      <div className="p-6 border-b border-[#2e3345]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/30">
            <Zap className="w-5 h-5 fill-current" />
          </div>
          <div>
            <span className="text-xl font-bold text-white tracking-tight">RazorBuy</span>
            <span className="block text-[10px] font-semibold tracking-wider text-indigo-400 uppercase">
              Agentic Commerce
            </span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1.5">
        {nav.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3.5 py-3 rounded-xl text-sm font-medium transition-all ${
                active
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/30"
                  : "text-gray-400 hover:bg-[#242836] hover:text-white"
              }`}
            >
              <item.icon className={`w-4 h-4 ${active ? "text-white" : "text-gray-400"}`} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer Thesis */}
      <div className="p-4 m-4 rounded-xl bg-[#242836] border border-[#2e3345] text-xs">
        <p className="font-semibold text-gray-300">Core Thesis:</p>
        <p className="mt-1 text-[11px] text-indigo-300 italic leading-relaxed">
          &quot;Autonomous reasoning does not imply autonomous financial authority.&quot;
        </p>
      </div>
    </aside>
  );
}