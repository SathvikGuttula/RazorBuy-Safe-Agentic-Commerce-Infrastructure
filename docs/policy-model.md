# RazorBuy Policy Engine Specification

The Policy Engine serves as the financial boundary for agentic transactions.

---

## Policy Schema

Each merchant maintains a versioned policy record in PostgreSQL:

```json
{
  "max_autonomous_transaction_amount": 3000.00,
  "max_discount_percent": 10.00,
  "max_discount_amount": 300.00,
  "negotiation_enabled": true,
  "auto_purchase_enabled": true,
  "confirmation_threshold": 5000.00,
  "max_payment_attempts": 2,
  "refund_requires_human": true,
  "restricted_categories": ["restricted_cat"],
  "restricted_products": []
}