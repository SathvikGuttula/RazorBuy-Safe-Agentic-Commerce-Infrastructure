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
git clone https://github.com/SathvikGuttula/RazorBuy-Safe-Agentic-Commerce-Infrastructure.git
cd razorbuy
cp .env.example .env
```

### 2. Start PostgreSQL (Docker)

```bash
docker compose up -d
```

### 3. Set Up & Seed Backend

```bash
cd backend
python -m venv .venv
# On Windows:
.\.venv\Scripts\Activate.ps1
# On Linux/WSL:
source .venv/bin/activate

pip install -r requirements.txt
python seed_db.py
```

Start the backend from the repository root with the location-independent launcher:

```powershell
.\backend\scripts\start_backend.ps1
```

### 4. Start Next.js Frontend

```bash
# In a new terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

## 🧪 Running Automated Tests & Benchmark

```bash
# Run unit and integration tests
cd backend
python -m pytest -v --tb=short

# Run the automated safety evaluation
python ..\evaluation\benchmark.py
```

## 📂 Repository Structure

```text
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
```

## 📜 License
MIT License. Built for the Razorpay AI Builder Internship Buildathon 2026.