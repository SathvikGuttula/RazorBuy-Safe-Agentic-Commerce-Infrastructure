"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function AuditPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .getAuditLog(filter ? `status=${filter}&limit=100` : "limit=100")
      .then((data: any) => {
        setEvents(data.events || []);
        setTotal(data.total || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Audit Trail</h1>
          <p className="text-sm text-[var(--text-dim)] mt-1">
            {total} total events — Append-only, immutable ledger
          </p>
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="bg-[var(--surface)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All Statuses</option>
          <option value="SUCCESS">Success</option>
          <option value="BLOCKED">Blocked</option>
          <option value="FAILED">Failed</option>
          <option value="ESCALATED">Escalated</option>
        </select>
      </div>

      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-[var(--text-dim)]">
              <th className="text-left p-3">Timestamp</th>
              <th className="text-left p-3">Actor</th>
              <th className="text-left p-3">Action</th>
              <th className="text-left p-3">Resource</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Reason Codes</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e: any) => (
              <tr key={e.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface2)]">
                <td className="p-3 text-xs text-[var(--text-dim)] font-mono">
                  {new Date(e.timestamp).toLocaleString()}
                </td>
                <td className="p-3">
                  <span className="px-2 py-0.5 bg-[var(--surface2)] rounded text-xs">
                    {e.actor}
                  </span>
                </td>
                <td className="p-3 font-mono text-xs">{e.action}</td>
                <td className="p-3 text-xs text-[var(--text-dim)]">
                  {e.resource_type}
                  {e.resource_id ? `:${e.resource_id.slice(0, 8)}` : ""}
                </td>
                <td className="p-3">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      e.status === "SUCCESS"
                        ? "bg-green-900/50 text-green-400"
                        : e.status === "BLOCKED"
                        ? "bg-red-900/50 text-red-400"
                        : e.status === "FAILED"
                        ? "bg-orange-900/50 text-orange-400"
                        : e.status === "ESCALATED"
                        ? "bg-yellow-900/50 text-yellow-400"
                        : "bg-blue-900/50 text-blue-400"
                    }`}
                  >
                    {e.status}
                  </span>
                </td>
                <td className="p-3 text-xs text-[var(--text-dim)] max-w-xs truncate">
                  {e.reason_codes?.join(", ") || "—"}
                </td>
              </tr>
            ))}
            {events.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className="p-8 text-center text-[var(--text-dim)]">
                  No audit events found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}