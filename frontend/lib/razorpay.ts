export function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") return resolve(false);
    if ((window as any).Razorpay) return resolve(true);

    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

export async function openRazorpayCheckout({
  key,
  orderId,
  providerOrderId,
  amount,
  currency = "INR",
  name = "RazorBuy Merchant",
  description = "Agentic Commerce Order",
  onSuccess,
  onFailure,
}: {
  key?: string;
  orderId: string;
  providerOrderId: string;
  amount: number;
  currency?: string;
  name?: string;
  description?: string;
  onSuccess: (response: {
    razorpay_order_id: string;
    razorpay_payment_id: string;
    razorpay_signature: string;
  }) => void;
  onFailure?: (error: any) => void;
}) {
  const isRealKey = key && key.startsWith("rzp_test_") && !key.includes("placeholder");

  if (isRealKey) {
    const loaded = await loadRazorpayScript();
    if (loaded) {
      try {
        const options = {
          key: key,
          amount: Math.round(amount * 100),
          currency: currency,
          name: name,
          description: description,
          order_id: providerOrderId,
          handler: function (response: any) {
            onSuccess({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
          },
          prefill: {
            name: "Test Buyer",
            email: "buyer@razorbuy.demo",
            contact: "9999999999",
          },
          theme: { color: "#6366f1" },
          modal: {
            ondismiss: function () {
              if (onFailure) onFailure({ reason: "dismissed" });
            },
          },
        };
        const rzp = new (window as any).Razorpay(options);
        rzp.open();
        return;
      } catch (err) {
        console.warn("Razorpay Checkout.js error, falling back to mock signature:", err);
      }
    }
  }

  // Mock / Test Fallback Signature for local development
  const mockPaymentId = `pay_simulated_${Date.now()}`;
  onSuccess({
    razorpay_order_id: providerOrderId,
    razorpay_payment_id: mockPaymentId,
    razorpay_signature: "mock_signature",
  });
}