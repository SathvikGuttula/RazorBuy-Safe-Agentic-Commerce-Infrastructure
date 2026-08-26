const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail?.message || err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  // Catalog
  searchProducts: (params: string) =>
    fetchAPI<any>(`/products?${params}`),
  getProduct: (id: string) =>
    fetchAPI<any>(`/products/${id}`),

  // Orders
  createOrder: (data: any) =>
    fetchAPI<any>("/orders", { method: "POST", body: JSON.stringify(data) }),
  getOrders: () =>
    fetchAPI<any>("/orders"),
  getOrder: (id: string) =>
    fetchAPI<any>(`/orders/${id}`),
  confirmOrder: (id: string) =>
    fetchAPI<any>(`/orders/${id}/confirm`, { method: "POST" }),
  cancelOrder: (id: string) =>
    fetchAPI<any>(`/orders/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: "Cancelled via dashboard" }),
    }),

  // Payments
  createPayment: (orderId: string) =>
    fetchAPI<any>("/payments/create", {
      method: "POST",
      body: JSON.stringify({ order_id: orderId }),
    }),
  verifyPayment: (data: any) =>
    fetchAPI<any>("/payments/verify", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Policies
  getPolicy: () => fetchAPI<any>("/policies"),
  updatePolicy: (data: any) =>
    fetchAPI<any>("/policies", { method: "PUT", body: JSON.stringify(data) }),

  // Audit
  getAuditLog: (params?: string) =>
    fetchAPI<any>(`/audit${params ? `?${params}` : ""}`),
  getAuditSummary: () => fetchAPI<any>("/audit/summary"),

  // Agent
  chat: (message: string, sessionId?: string) =>
    fetchAPI<any>("/agent/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    }),
};