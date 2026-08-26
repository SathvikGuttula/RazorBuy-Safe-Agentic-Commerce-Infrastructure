"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { openRazorpayCheckout } from "@/lib/razorpay";
import {
  ShoppingCart,
  RefreshCw,
  CreditCard,
  ShieldCheck,
} from "lucide-react";

export default function OrdersPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [payingOrderId, setPayingOrderId] = useState<string | null>(null);

  const loadOrders = useCallback(() => {
    setLoading(true);
    api
      .getAuditLog("resource_type=order&limit=50")
      .then((data: any) => {
        setEvents(data.events || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Load immediately + auto-refresh every 3s + refresh on visibility
  useEffect(() => {
    loadOrders();
    const interval = setInterval(loadOrders, 3000);

    const onVisibility = () => {
      if (!document.hidden) loadOrders();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [loadOrders]);

  const handlePayOrder = async (orderId: string) => {
    setPayingOrderId(orderId);
    try {
      const payRes = await api.createPayment(orderId);
      await openRazorpayCheckout({
        key: payRes.key_id || "rzp_test_placeholder",
        orderId: orderId,
        providerOrderId: payRes.provider_order_id,
        amount: payRes.amount,
        name: "RazorBuy Test Checkout",
        description: `Order ${orderId.slice(0, 8)}`,
        onSuccess: async (verifyData) => {
          try {
            await api.verifyPayment({
              order_id: orderId,
              razorpay_order_id: verifyData.razorpay_order_id,
              razorpay_payment_id: verifyData.razorpay_payment_id,
              razorpay_signature: verifyData.razorpay_signature,
            });
            alert("✅ Payment Verified! Order status updated to PAID.");
            loadOrders();
          } catch (e: any) {
            alert(`Verification: ${e.message}`);
          }
        },
        onFailure: () => {},
      });
    } catch (err: any) {
      alert(`Payment error: ${err.message}`);
    } finally {
      setPayingOrderId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ShoppingCart className="w-6 h-6 text-indigo-400" />
            Order Ledger
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Real-time status of orders evaluated by the Policy Engine (auto-refreshes)
          </p>
        </div>
        <button
          onClick={loadOrders}
          disabled={loading}
          className="flex items-center gap-2 bg-[#1a1d27] hover:bg-[#242836] border border-[#2e3345] text-gray-200 px-4 py-2 rounded-xl text-sm transition-all"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Refreshing..." : "Refresh Now"}
        </button>
      </div>

      <div className="bg-[#1a1d27] border border-[#2e3345] rounded-xl overflow-hidden shadow-xl">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#2e3345] text-gray-400 bg-[#242836]/50">
              <th className="text-left p-4 font-semibold">Time</th>
              <th className="text-left p-4 font-semibold">Order ID</th>
              <th className="text-left p-4 font-semibold">Action</th>
              <th className="text-left p-4 font-semibold">Policy Result</th>
              <th className="text-left p-4 font-semibold">Reason Codes</th>
              <th className="text-right p-4 font-semibold">Action</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e: any) => (
              <tr
                key={e.id}
                className="border-b border-[#2e3345] last:border-0 hover:bg-[#242836]/40 transition-colors"
              >
                <td className="p-4 text-xs font-mono text-gray-400">
                  {new Date(e.timestamp).toLocaleString()}
                </td>
                <td className="p-4 font-mono text-xs font-medium text-indigo-300">
                  {e.resource_id ? e.resource_id.slice(0, 8) : "—"}...
                </td>
                <td className="p-4 font-mono text-xs">{e.action}</td>
                <td className="p-4">
                  <span
                    className={`px-2.5 py-1 rounded-md text-xs font-semibold ${
                      e.result === "APPROVED" || e.result === "SUCCESS"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : e.result === "REJECTED" || e.result === "BLOCKED"
                        ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                        : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                    }`}
                  >
                    {e.result}
                  </span>
                </td>
                <td className="p-4 text-xs text-gray-400 max-w-xs truncate">
                  {e.reason_codes?.join(", ") || "—"}
                </td>
                <td className="p-4 text-right">
                  {e.result === "APPROVED" && e.action === "CREATE_ORDER" && (
                    <button
                      onClick={() => handlePayOrder(e.resource_id)}
                      disabled={payingOrderId === e.resource_id}
                      className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-3 py-1.5 rounded-lg font-medium transition-all shadow-md shadow-indigo-600/20 flex items-center gap-1.5 ml-auto"
                    >
                      <CreditCard className="w-3.5 h-3.5" />
                      {payingOrderId === e.resource_id ? "Processing..." : "Pay via Razorpay"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {events.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className="p-12 text-center text-gray-500">
                  No orders recorded yet. Go to AI Chat to create orders.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}