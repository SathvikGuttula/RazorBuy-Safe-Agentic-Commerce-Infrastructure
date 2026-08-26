# RazorBuy REST API Reference

All endpoints return JSON and are prefixed with `/api`.

---

## Catalog API

### `GET /api/products`
Search and filter products.

**Query Parameters:**
* `query` (string, optional): Search keyword
* `category` (string, optional): Category filter
* `max_price` (float, optional): Price cap in INR
* `has_feature` (string, optional): Feature flag (e.g. `anc`)

### `GET /api/products/{id_or_sku}`
Fetch single product details by SKU or UUID.

---

## Policy API

### `GET /api/policies`
Fetch active merchant policy.

### `PUT /api/policies`
Update merchant policy (creates a new policy version).

### `POST /api/policies/evaluate`
Evaluate a financial action against merchant policy rules.

---

## Orders API

### `POST /api/orders`
Create a new purchase order. Automatically checks inventory and policy.

```json
{
  "product_id": "P101",
  "quantity": 1,
  "discount_amount": 0.0
}