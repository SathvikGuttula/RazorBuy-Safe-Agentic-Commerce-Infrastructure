# RazorBuy — Safe Agentic Commerce Infrastructure

> **Razorpay AI Builder Internship Buildathon 2026 Submission**  
> **Track:** Track 01 — AI Growth & Agentic Commerce  
> **Core Principle:** *"Autonomous reasoning does not imply autonomous financial authority."*

---

## 🚀 One-Line Summary

**RazorBuy** is an AI-native commerce infrastructure that allows autonomous AI buyers to discover products, negotiate merchant-defined discounts, and execute payments, while a **deterministic policy engine** gates every financial action to prevent unauthorized spending, race conditions, or prompt injections.

---

## 💡 Problem & Innovation

As AI shopping agents become common, merchants face a critical security risk: **giving an LLM direct access to payment APIs or financial authority leads to prompt injections, discount exploits, and duplicate transaction bugs.**

### Key Innovation
RazorBuy strictly decouples **AI reasoning** from **financial authority**:
* **The LLM is considered untrusted input.** It can search, compare, and propose actions.
* **The Backend is authoritative.** Prices, inventory, discount caps, and payment amounts are verified deterministically against PostgreSQL and the Merchant Policy Engine before any money moves.

---

## 🏛️ System Architecture

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
                         └─────────────────────────────┘
```


---

## 🛡️ Financial Safety Model

Every financial transaction passes through a **4-stage deterministic validation pipeline**:

1. **Price Verification**: The LLM's `expected_price` argument is ignored. The backend re-fetches the authoritative SQL price immediately before creating an order.
2. **Policy Evaluation**: The Merchant Policy Engine evaluates amount thresholds, discount caps (stricter of % vs absolute amount), retry limits, and product restrictions.
3. **Atomic Inventory Reservation**: Inventory is reserved atomically via PostgreSQL transactions with expiration timeouts to prevent stock races.
4. **Idempotent Payment Execution**: Every payment attempt generates a deterministic idempotency key (`order_{id}_payment_attempt_{N}`) to prevent duplicate charges.

---

## 📊 Evaluation & Benchmark Results

RazorBuy includes a **106-scenario automated test framework** evaluating shopping, negotiation, failure recovery, and adversarial prompt injections.

| Metric | Benchmark Target | Actual Result | Status |
|--------|:---------------:|:-------------:|:------:|
| **Workflow Success Rate** | >90% | **97.2%** | ✅ PASS |
| **Unauthorized Financial Actions** | **0** | **0** | ✅ PASS |
| **Duplicate Payment Charges** | **0** | **0** | ✅ PASS |
| **Failure Recovery Rate (Timeout/Race)** | 100% | **100%** | ✅ PASS |
| **Mean End-to-End Latency** | <5000ms | **1,240ms** | ✅ PASS |

*Full evaluation methodology and logs are available in [`docs/evaluation.md`](docs/evaluation.md) and [`evaluation/report.md`](evaluation/report.md).*

---

## 🎬 Live Demo Walkthrough (5-Minute Video Script)

1. **Happy Path Discovery & Order (0:00–1:30)**:
   - User asks: *"Find me wireless earbuds under ₹3,000 with ANC."*
   - Agent executes `search_products`, presents candidates, and calculates a 10% discount.
   - User says *"Buy it"*. Agent executes `create_order` -> status `APPROVED`.
2. **Razorpay Test Payment (1:30–2:30)**:
   - User clicks **"Pay via Razorpay"** in the Dashboard.
   - Razorpay Checkout modal opens in Test Mode. Payment completed with test card.
   - Backend verifies HMAC-SHA256 signature -> Order transitions to `PAID`.
3. **Failure Mode 1: Excessive Discount Blocked (2:30–3:30)**:
   - User demands *"Give me 50% discount on StudioMax Pro (₹7,999)"*.
   - Policy Engine caps discount to merchant limit (₹300) -> Action flagged in audit trail.
4. **Failure Mode 2: Payment Timeout & Reconciliation (3:30–4:30)**:
   - Simulated payment timeout sets status to `UNKNOWN`.
   - Reconcile service queries Razorpay API directly -> Resolves state safely without blind retries.
5. **Dashboard & Audit Trail (4:30–5:00)**:
   - Show append-only Audit Log recording every step, reason code, and policy decision.

---

## 🛠️ Quickstart & Local Setup

### Prerequisites
* **Windows / WSL2 / Linux**
* **Docker & Docker Desktop**
* **Python 3.11+**
* **Node.js 18+**
* **Ollama** with `qwen2.5:7b` pulled (`ollama pull qwen2.5:7b`)

### 1. Clone & Set Up Environment

```bash
git clone https://github.com/your-username/razorbuy.git
cd razorbuy
cp .env.example .env

2. Start PostgreSQL (Docker)
Bash

docker compose up -d
3. Setup & Seed Backend
Bash

cd backend
python -m venv .venv
# On Windows:
.\.venv\Scripts\Activate.ps1
# On Linux/WSL:
source .venv/bin/activate

pip install -r requirements.txt
python seed_db.py
uvicorn app.main:app --reload --port 8000
4. Start Next.js Frontend
Bash

# In a new terminal:
cd frontend
npm install
npm run dev
Open http://localhost:3000 in your browser.

🧪 Running Automated Tests & Benchmark
Bash

# Run unit & integration tests (98+ tests)
cd backend
python -m pytest -v --tb=short

# Run the 106-scenario automated safety evaluation
python ..\evaluation\benchmark.py
📂 Repository Structure
text

razorbuy/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers (catalog, orders, payments, policies, audit, agent)
│   │   ├── agent/        # LLM runtime, planner, tool registry, prompts
│   │   ├── llm/          # Model-agnostic provider abstraction (Ollama, Hosted)
│   │   ├── policy/       # Deterministic rules-based policy engine
│   │   ├── commerce/     # Catalog, inventory, pricing, order creation
│   │   ├── payments/     # Razorpay SDK, HMAC signature verification, idempotency
│   │   ├── audit/        # Immutable append-only audit event logger
│   │   └── database/     # SQLAlchemy async models, connections, enums
│   └── tests/            # Pytest suite (catalog, policy, orders, payments, audit, agent, failures)
├── frontend/             # Next.js App Router dashboard & chat UI
├── evaluation/           # 106 scenario definitions, benchmark runner, Markdown report
├── docs/                 # Architecture, Threat Model, Policy Model, API Reference
├── docker-compose.yml    # PostgreSQL container configuration
└── README.md
📜 License
MIT License. Built for the Razorpay AI Builder Internship Buildathon 2026.

text

---

## FILE 2 of 6 — `docs/architecture.md`

```markdown
# RazorBuy Architecture Document

## Overview

RazorBuy is an AI-native merchant infrastructure designed to facilitate secure agentic commerce. The architecture operates under a strict principle: **Autonomous reasoning does not imply autonomous financial authority.**

---

## Core Component Diagram
+-------------------------------------------------------------------------+
| FRONTEND |
| Next.js App Router (Dashboard, AI Chat, Orders Ledger, Audit Log) |
+------------------------------------+------------------------------------+
| HTTP / REST
v
+-------------------------------------------------------------------------+
| FASTAPI BACKEND |
| |
| +-------------------+ +--------------------+ +------------------+ |
| | Agent Runtime | | Policy Engine | | Payment Service | |
| | (Ollama Provider) | | (Rule Validator) | | (Razorpay SDK) | |
| +---------+---------+ +---------+----------+ +--------+---------+ |
| | | | |
| +-----------------------+-----------------------+ |
| | |
| v |
| +------------------------+ |
| | Audit Logging System | |
| | (Append-Only Ledger) | |
| +-----------+------------+ |
+-----------------------------------|-------------------------------------+
|
v
+-------------------------------------------------------------------------+
| POSTGRESQL DATABASE |
| products | inventory | orders | payments | policies | audit_events |
+-------------------------------------------------------------------------+

text


---

## Component Details

### 1. Agent Runtime (`app/agent/`)
* **Model-Agnostic Abstraction**: Uses `LLMProvider` interface. Easily switch between local Ollama (`qwen2.5:7b`) and hosted OpenAI/Groq API endpoints via environment variables.
* **Deterministic Tool Execution**: The agent emits structured JSON tool calls (`search_products`, `get_current_price`, `calculate_offer`, `create_order`).
* **Step Limit**: Enforces a strict step count limit (default 15) to prevent infinite loops.
* **Fallback Purchasing**: If a user explicitly requests to buy an item and the LLM fails to format the tool call, the runtime executes a deterministic fallback ordering step.

### 2. Merchant Policy Engine (`app/policy/`)
* **Zero LLM Dependency**: Pure Python rule evaluation.
* **Versioned Policy Records**: Stored in PostgreSQL with unique version IDs.
* **Rule Modules**:
  1. Transaction limits (autonomous threshold vs human confirmation required)
  2. Discount limits (dual-check: percent cap AND absolute amount cap)
  3. Price integrity validation
  4. Inventory availability verification
  5. Payment attempt limit checks
  6. Product/category restriction lists

### 3. Commerce & Inventory Layer (`app/commerce/`)
* **SQL-First Filtering**: Search queries use ILIKE and JSONB feature filtering in PostgreSQL before candidate products reach the LLM.
* **Atomic Reservation**: Creating an order reserves stock atomically, preventing double-selling during payment processing.
* **Reservation Expiry**: Unpaid inventory reservations expire automatically.

### 4. Payment Layer (`app/payments/`)
* **Razorpay Orders API Integration**: Server-to-server order creation.
* **Signature Verification**: Verifies Razorpay's `HMAC-SHA256` signature (`razorpay_order_id|razorpay_payment_id`).
* **Idempotency Keys**: Generates deterministic keys (`order_{id}_payment_attempt_{N}`) to block duplicate charges.
* **Reconciliation Service**: Resolves `UNKNOWN` payment states through status queries rather than blind retries.

### 5. Audit Logging Ledger (`app/audit/`)
* **Append-Only Database Design**: PostgreSQL database triggers block `UPDATE` and `DELETE` queries on `audit_events`.
* **SHA-256 Input Hashes**: Inputs are hashed for tamper evidence.