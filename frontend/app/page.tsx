"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  ShieldCheck,
  ShieldAlert,
  CreditCard,
  AlertTriangle,
  Activity,
  Users,
} from "lucide-react";

export default function OverviewPage() {
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getAuditSummary()
      .then(setSummary)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-[var(--text-dim)]">
        Loading dashboard...
      </div>
    );
  }

  const stats = [
    {
      label: "Total Events",
      value: summary?.total_events ?? 0,
      icon: Activity,
      color: "text-blue-400",
    },
    {
      label: "Blocked Actions",
      value: summary?.blocked_actions ?? 0,
      icon: ShieldAlert,
      color: "text-red-400",
    },
    {
      label: "Successful Payments",
      value: summary?.successful_payments ?? 0,
      icon: CreditCard,
      color: "text-green-400",
    },
    {
      label: "Failed Payments",
      value: summary?.failed_payments ?? 0,
      icon: AlertTriangle,
      color: "text-orange-400",
    },
    {
      label: "Policy Violations",
      value: summary?.policy_violations ?? 0,
      icon: ShieldCheck,
      color: "text-purple-400",
    },
    {
      label: "Agent Sessions",
      value: summary?.agent_sessions ?? 0,
      icon: Users,
      color: "text-cyan-400",
    },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Merchant Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {stats.map((s) => (
          <div
            key={s.label}
            className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-[var(--text-dim)]">{s.label}</span>
              <s.icon className={`w-5 h-5 ${s.color}`} />
            </div>
            <p className="text-3xl font-bold">{s.value}</p>
          </div>
        ))}
      </div>

      <h2 className="text-lg font-semibold mb-4">Recent Audit Events</h2>
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-[var(--text-dim)]">
              <th className="text-left p-3">Time</th>
              <th className="text-left p-3">Actor</th>
              <th className="text-left p-3">Action</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Reasons</th>
            </tr>
          </thead>
          <tbody>
            {(summary?.recent_events ?? []).map((e: any) => (
              <tr
                key={e.id}
                className="border-b border-[var(--border)] last:border-0"
              >
                <td className="p-3 text-[var(--text-dim)]">
                  {new Date(e.timestamp).toLocaleTimeString()}
                </td>
                <td className="p-3">{e.actor}</td>
                <td className="p-3 font-mono text-xs">{e.action}</td>
                <td className="p-3">
                  <StatusBadge status={e.status} />
                </td>
                <td className="p-3 text-xs text-[var(--text-dim)]">
                  {e.reason_codes?.join(", ") || "—"}
                </td>
              </tr>
            ))}
            {(!summary?.recent_events?.length) && (
              <tr>
                <td colSpan={5} className="p-8 text-center text-[var(--text-dim)]">
                  No events yet. Start a chat to generate activity.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    SUCCESS: "bg-green-900/50 text-green-400",
    BLOCKED: "bg-red-900/50 text-red-400",
    FAILED: "bg-orange-900/50 text-orange-400",
    ESCALATED: "bg-yellow-900/50 text-yellow-400",
    PENDING: "bg-blue-900/50 text-blue-400",
  };
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium ${
        colors[status] || "bg-gray-800 text-gray-400"
      }`}
    >
      {status}
    </span>
  );
}