"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Save, Shield } from "lucide-react";

export default function PoliciesPage() {
  const [policy, setPolicy] = useState<any>(null);
  const [form, setForm] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getPolicy().then((data) => {
      setPolicy(data);
      setForm(data);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await api.updatePolicy({
        max_autonomous_transaction_amount: Number(form.max_autonomous_transaction_amount),
        max_discount_percent: Number(form.max_discount_percent),
        max_discount_amount: Number(form.max_discount_amount),
        negotiation_enabled: form.negotiation_enabled,
        auto_purchase_enabled: form.auto_purchase_enabled,
        confirmation_threshold: Number(form.confirmation_threshold),
        max_payment_attempts: Number(form.max_payment_attempts),
        refund_requires_human: form.refund_requires_human,
      });
      setPolicy(updated);
      setForm(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      alert("Failed to save policy");
    } finally {
      setSaving(false);
    }
  };

  if (!policy) {
    return <div className="text-[var(--text-dim)]">Loading policy...</div>;
  }

  const fields = [
    { key: "max_autonomous_transaction_amount", label: "Max Autonomous Transaction (₹)", type: "number" },
    { key: "max_discount_percent", label: "Max Discount (%)", type: "number" },
    { key: "max_discount_amount", label: "Max Discount Amount (₹)", type: "number" },
    { key: "confirmation_threshold", label: "Confirmation Threshold (₹)", type: "number" },
    { key: "max_payment_attempts", label: "Max Payment Attempts", type: "number" },
  ];

  const toggles = [
    { key: "negotiation_enabled", label: "Negotiation Enabled" },
    { key: "auto_purchase_enabled", label: "Auto-Purchase Enabled" },
    { key: "refund_requires_human", label: "Refund Requires Human Approval" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Shield className="w-6 h-6 text-[var(--accent)]" />
            Merchant Policy
          </h1>
          <p className="text-sm text-[var(--text-dim)] mt-1">
            Version {policy.version} — All financial actions are gated by these rules
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white px-4 py-2 rounded-lg text-sm"
        >
          <Save className="w-4 h-4" />
          {saved ? "Saved!" : saving ? "Saving..." : "Save Policy"}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6">
          <h2 className="font-semibold mb-4">Financial Limits</h2>
          <div className="space-y-4">
            {fields.map((f) => (
              <div key={f.key}>
                <label className="text-sm text-[var(--text-dim)] block mb-1">
                  {f.label}
                </label>
                <input
                  type={f.type}
                  value={form[f.key] ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, [f.key]: e.target.value })
                  }
                  className="w-full bg-[var(--surface2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
                />
              </div>
            ))}
          </div>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6">
          <h2 className="font-semibold mb-4">Feature Toggles</h2>
          <div className="space-y-4">
            {toggles.map((t) => (
              <div key={t.key} className="flex items-center justify-between">
                <span className="text-sm">{t.label}</span>
                <button
                  onClick={() =>
                    setForm({ ...form, [t.key]: !form[t.key] })
                  }
                  className={`w-12 h-6 rounded-full transition-colors relative ${
                    form[t.key] ? "bg-[var(--accent)]" : "bg-[var(--surface2)]"
                  }`}
                >
                  <div
                    className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-transform ${
                      form[t.key] ? "translate-x-6" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
            ))}
          </div>

          <div className="mt-8 p-4 bg-[var(--surface2)] rounded-lg">
            <h3 className="text-sm font-semibold mb-2">How It Works</h3>
            <ul className="text-xs text-[var(--text-dim)] space-y-1">
              <li>• Transactions ≤ autonomous limit → auto-approved</li>
              <li>• Transactions &gt; limit but ≤ threshold → user confirmation</li>
              <li>• Transactions &gt; threshold → blocked</li>
              <li>• Discounts capped to stricter of % or amount limit</li>
              <li>• LLM output is never trusted for financial data</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}