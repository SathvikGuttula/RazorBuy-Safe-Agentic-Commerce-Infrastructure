# RazorBuy — Architecture Specification

## Executive Summary

RazorBuy is an AI-native merchant infrastructure designed to facilitate secure agentic commerce. The architecture operates under a strict principle: **Autonomous reasoning does not imply autonomous financial authority.**

The LLM is responsible for intent understanding, product discovery, comparison, and recommendation. Deterministic backend systems handle all pricing, inventory reservation, policy enforcement, order state management, and payment execution.

---

## System Architecture Diagram

```text
                         ┌─────────────────────────────┐
                         │     User / AI Buyer Chat    │
                         └──────────────┬──────────────┘
                                        │ Natural Language
                                        ▼
                         ┌─────────────────────────────┐
                         │      Agent Runtime (LLM)    │
                         │     (Ollama / Qwen2.5-7B)   │
                         └──────────────┬──────────────┘
                                        │ Structured Tool Call
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           DETERMINISTIC BACKEND                              │
│                                                                              │
│  ┌────────────────────┐    ┌────────────────────┐    ┌────────────────────┐  │
│  │   Catalog Service  │───▶│    Policy Engine   │───▶│   Payment Service  │  │
│  │  (Authoritative SQL)│   │ (Rules & Spend Caps)│   │ (Razorpay Integration)│ │
│  └────────────────────┘    └────────────────────┘    └────────────────────┘  │
│                                                                              │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │ Append-Only Event
                                       ▼
                         ┌─────────────────────────────┐
                         │      Immutable Audit Log    │
                         │       (PostgreSQL Ledger)   │
                         └──────────────┬──────────────┘
                                       │ Real-Time Stream
                                       ▼
                         ┌─────────────────────────────┐
                         │       Merchant Dashboard   │
                         │       (Next.js App Router)  │
                         └─────────────────────────────┘
```


---

## Component Deep Dive

### 1. Agent Runtime (`app/agent/`)

* **Model-Agnostic Abstraction**: Implements an `LLMProvider` interface (`app/llm/base.py`). The active model can be swapped from local Ollama (`qwen2.5:7b`) to hosted OpenAI/Groq API endpoints by changing `LLM_PROVIDER` in `.env`.
* **Structured Tool Execution**: Exposes 8 narrowly defined tool schemas (`search_products`, `get_product`, `check_inventory`, `get_current_price`, `calculate_offer`, `create_order`, `get_order`, `cancel_order`).
* **Step Limit Guard**: Enforces a maximum step count per user interaction (default 15) to prevent agent loops.
* **Deterministic Fallback**: If a user explicitly requests a purchase ("buy P101") and the LLM fails to invoke `create_order`, the runtime automatically invokes `create_order` using the last mentioned product SKU.
* **Multi-Turn State**: Reconstructs session history from PostgreSQL `agent_sessions` to maintain state across user turns.

### 2. Merchant Policy Engine (`app/policy/`)

* **Zero LLM Involvement**: Built entirely in Python as pure, deterministic business logic. The LLM cannot influence, bypass, or alter policy decisions.
* **Versioned Records**: Policies are stored in PostgreSQL with unique version numbers. Updates create a new version record (`version = version + 1`), preserving historical compliance.
* **Rule Pipeline**:
  1. **Transaction Amount Check**: Compares total against merchant limit and user autonomous spending cap. Triggers `AWAITING_CONFIRMATION` or `BLOCKED` if exceeded.
  2. **Discount Limit Check**: Dual constraint — evaluates `max_discount_percent` AND `max_discount_amount`. The stricter limit caps the allowed discount.
  3. **Price Integrity Check**: Re-fetches current database price immediately before order creation to ensure zero discrepancy.
  4. **Inventory Availability Check**: Verifies warehouse stock levels before approving purchase intents.
  5. **Payment Retry Check**: Enforces maximum payment attempts (default 2) to prevent card/gateway abuse.
  6. **Restriction Check**: Evaluates blacklisted category and product UUID lists.

### 3. Commerce & Inventory Layer (`app/commerce/`)

* **SQL-First Catalog Search**: Performs deterministic SQL queries (using `ILIKE` and `JSONB` feature matching) to narrow results before sending top candidates to the LLM.
* **Atomic Inventory Reservation**: On order creation, inventory is decremented from `available_quantity` and added to `reserved_quantity` within a database transaction.
* **Reservation Timeout**: Each reservation receives an expiration timestamp (`expires_at`). Expired reservations release stock back to available inventory.

### 4. Payment Layer (`app/payments/`)

* **Razorpay Orders API**: Generates server-to-server Razorpay orders (`POST /v1/orders`) with exact amount in paise.
* **Cryptographic Verification**: Verifies Razorpay's `HMAC-SHA256` payment signature (`razorpay_order_id|razorpay_payment_id`) against `RAZORPAY_KEY_SECRET`.
* **Idempotency Enforcer**: Generates deterministic idempotency keys (`order_{id}_payment_attempt_{N}`) to guarantee duplicate requests return existing payment records rather than creating new charges.
* **Reconciliation Engine**: Handles network/gateway timeouts (`UNKNOWN` status) by querying Razorpay's API to resolve state safely, adhering to a "Fail Closed" design.

### 5. Audit Logging Ledger (`app/audit/`)

* **Append-Only Database Schema**: PostgreSQL triggers (`audit_no_update`, `audit_no_delete`) block all `UPDATE` and `DELETE` queries on the `audit_events` table at the database level.
* **Input Hashes**: SHA-256 hashes of input payloads are recorded alongside events for tamper evidence.
* **Reconstructable Trail**: Every agent step, tool call, policy evaluation, order status change, and payment verification is logged with timestamp, actor, result, and reason codes.

---

## Data Model (Entity Relationship Summary)
```text
[Users] 1 ─── N [AgentSessions] 1 ─── N [AgentActions]
  │
  ├── 1 ─── N [Orders] 1 ─── N [Payments]
  │
  └── 1 ─── N [InventoryReservations]

[Merchants] 1 ─── N [Products] 1 ─── 1 [Inventory]
  │
  └── 1 ─── N [MerchantPolicies]
```


---

## Order State Machine
```text
        DRAFT
         │
         ▼
    PENDING_POLICY
      /       \
  (Allowed)    (Over Limit)
     /           \
    ▼             ▼
  APPROVED     AWAITING_CONFIRMATION
    │             │
    │         (User Confirms)
    │             │
    └───┬─────────┘
       │
       ▼
  PAYMENT_PENDING
       │
       ▼
  PAYMENT_PROCESSING
    /          \
(Success)     (Failure/Timeout)
  /              \
  ▼                ▼
PAID        PAYMENT_FAILED / PAYMENT_UNKNOWN
  │                │
  ▼           (Reconcile)
COMPLETED         │
    └──────┬─────┘
        ▼
    PAID / CANCELLED
```


---

## Threat & Failure Summary

RazorBuy is hardened against:
- **Prompt Injection**: System prompt manipulation cannot bypass Python-level Policy Engine checks.
- **Price Race Conditions**: Price changes mid-checkout halt payment with `409 PRICE_CHANGED`.
- **Inventory Stock Races**: Exhausted stock halts payment with `409 INVENTORY_UNAVAILABLE`.
- **Duplicate Charges**: Idempotency keys prevent double billing on concurrent requests.
- **Payment Gateway Timeouts**: Reconciled via API query without blind retries.