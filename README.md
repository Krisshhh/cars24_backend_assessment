# AI Operations Copilot

A backend service that answers natural-language questions about customer orders
for a used-car marketplace, and explains contradictions between the order,
payment and delivery systems.

The interesting case is not "what is the status of order X". It is "the customer
says they paid but nothing is scheduled" — where three systems disagree and
somebody has to work out who is right before promising anything about a
customer's money.

**The core design decision: the language model never decides whether a
discrepancy exists.** A deterministic rules engine does that, in plain Python
with unit tests. The model translates questions into tool calls and findings into
prose. See [DESIGN.md](DESIGN.md) for the argument.

---

## Setup

```bash
git clone <repo-url> && cd cars24-ops-copilot
cp .env.example .env          # then put your API key in .env
docker compose up -d --build
docker compose exec api python -m seed.seed
docker compose exec api python -m pytest tests/ -q
```

Open **http://localhost:8000/** for the operator console.

The service runs without an API key. It falls back to the deterministic engine
and returns the same findings without the prose. See [Degraded mode](#degraded-mode).

### Environment

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@db:5432/copilot` | internal compose hostname |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | empty | required for prose answers |
| `OPENAI_API_KEY` | empty | only if `LLM_PROVIDER=openai` |
| `LLM_MODEL` | `claude-sonnet-4-6` | |
| `LLM_TIMEOUT_SECONDS` | `30` | |
| `MAX_TOOL_ITERATIONS` | `3` | tool-calling loop cap |
| `RATE_LIMIT_PER_WINDOW` | `20` | requests per window on `/query` |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `CONVERSATION_TTL_SECONDS` | `1800` | |
| `CONVERSATION_MAX_MESSAGES` | `8` | turns retained per conversation |

If port 5432 is taken locally, change the host mapping in `docker-compose.yml` to
`"5433:5432"`. `DATABASE_URL` does not change.

---

## Try it

Every scenario below is seeded at a fixed order id, so these run on a fresh
clone.

| Order | Vehicle | What is wrong | Ask |
| --- | --- | --- | --- |
| **4521** | Maruti Baleno, Rs 6,90,000 | Nothing. Healthy order. | `What's the payment status for order #4521?` |
| **1289** | Hyundai Creta, Rs 14,20,000 | Payment captured at the gateway 3h ago, webhook never processed, order still `PENDING_PAYMENT`, delivery unscheduled | `Customer says they've paid for order #1289 but delivery isn't scheduled - what's going on?` |
| **2231** | Tata Harrier, Rs 16,80,000 | Nothing. Token then balance, one delivery reschedule. | `Give me a full status summary for order #2231` |
| **3310** | Honda City, Rs 11,50,000 | Paid in full, delivery blocked on RC transfer at the RTO | `Why hasn't order #3310 been delivered yet?` |
| **7742** | Kia Seltos, Rs 12,40,000 | Booking token settled, balance outstanding, customer believes it is paid in full | `Customer of order #7742 insists they paid in full. Did they?` |
| **5108** | Tata Nexon, Rs 8,95,000 | Charged twice 68 seconds apart, refund initiated but not settled | `Was the customer on order #5108 charged more than once?` |
| **6003** | Maruti Ertiga, Rs 8,80,000 | Bank debited, gateway declined, customer holds a UTR the ledger cannot match | `Order #6003 - customer has a UTR but we show the payment failed` |

Expected for **1289**, the case the brief asks about: the answer confirms the
customer is correct, names the captured payment `pay_Qm3v7Lp42c`, identifies the
unprocessed webhook as the cause, and recommends replaying it. Both
`PAYMENT_RECONCILIATION_LAG` (critical) and `WEBHOOK_MISSING` (warning) appear,
critical first.

Expected for **4521** and **2231**: `clean: true`, no findings. A reconciliation
engine that flags everything is worthless, so these are the false-positive guard.

---

## API

| Method | Path | Uses the model | Purpose |
| --- | --- | --- | --- |
| `GET` | `/` | no | operator console |
| `POST` | `/query` | yes | natural-language entry point |
| `GET` | `/orders/{id}` | no | full order snapshot |
| `GET` | `/orders/{id}/diagnose` | **no** | rules-engine findings |
| `GET` | `/orders/{id}/timeline` | no | cross-system event log |
| `GET` | `/health` | no | liveness |
| `GET` | `/health/deps` | no | database and provider status |

Interactive docs at `/docs`.

`/orders/{id}/diagnose` is the source of truth. Call it directly to check that
`/query` is not embellishing.

### `POST /query`

```bash
curl -s -X POST http://localhost:8000/query \
  -H "content-type: application/json" \
  -d '{"query":"Customer says they have paid for order #1289 but delivery is not scheduled"}'
```

```json
{
  "answer": "...",
  "order_ids_resolved": [1289],
  "tools_called": [
    {"name": "run_discrepancy_check", "arguments": {"order_id": 1289}, "latency_ms": 8, "ok": true}
  ],
  "discrepancies": [
    {"code": "PAYMENT_RECONCILIATION_LAG", "severity": "CRITICAL", "title": "...",
     "detail": "...", "evidence": [...], "suggested_action": "..."}
  ],
  "facts_used": [
    "payments.id=193.status=CAPTURED",
    "payments.id=193.gateway_ref=pay_Qm3v7Lp42c",
    "orders.id=1289.status=PENDING_PAYMENT"
  ],
  "degraded": false,
  "iterations": 2,
  "request_id": "0c91a268-a2b3-4262-bfea-53092706fd86",
  "latency_ms": 3180
}
```

`tools_called` and `facts_used` exist so an operator can see what the answer rests
on before acting on it, and so a reviewer can falsify it. If a claim in `answer`
is not in `facts_used`, the model embellished.

Optional `conversation_id` (max 64 chars, `[A-Za-z0-9_.:-]`) retains the last 8
prose turns for 30 minutes.

Errors: `422` on an empty, oversized or malformed query. `429` with `Retry-After`
past the rate limit. Provider failures return `200` with `degraded: true`, never
a `500`.

### `GET /orders/{id}/diagnose`

```bash
curl -s http://localhost:8000/orders/1289/diagnose
```

Returns `{order_id, order_status, evaluated_at, clean, discrepancies[]}`. No model
involved, single-digit milliseconds, `404` on an unknown order.

---

## Degraded mode

If the model is unavailable — no key, timeout, 5xx, or the tool loop hitting its
cap — `/query` returns `200` with `degraded: true` and the raw rules-engine
findings instead of prose.

Verified with no key configured:

```
[deterministic engine only]  #1289  8 ms  0 model turns
CRITICAL  PAYMENT_RECONCILIATION_LAG
WARNING   WEBHOOK_MISSING
```

Same findings, same evidence, 8 milliseconds. The model is a presentation layer
over a system that works without it.

---

## Tests

```bash
docker compose exec api python -m pytest tests/ -q          # 130 tests
docker compose exec api python -m pytest tests/test_rules.py -q   # 30, no DB needed
```

| File | Tests | Needs a database |
| --- | --- | --- |
| `tests/test_rules.py` | 30 | **no** |
| `tests/test_repository.py` | 13 | yes |
| `tests/test_orchestrator.py` | 28 | yes |
| `tests/test_adversarial.py` | 59 | yes |

The rules tests run with the database stopped, in roughly 0.02 seconds, because
rules are pure functions over an in-memory snapshot. If that ever stops being
true, a rule has started doing IO.

```bash
docker compose stop db
docker compose exec api python -m pytest tests/test_rules.py -q   # still 30 passed
docker compose start db
```

`tests/test_orchestrator.py` tests the tool-calling loop with a scripted stub
provider, so the suite needs no API key and costs nothing to run.

---

## Layout

```
app/
├── models.py              SQLAlchemy models
├── repository.py          all database reads, ORM -> snapshot
├── schemas.py             request and response models
├── rules/
│   ├── types.py           snapshot dataclasses, Discrepancy, Evidence
│   ├── definitions.py     nine rules, pure functions, no IO
│   └── engine.py          registry runner, severity ordering
├── llm/
│   ├── provider.py        provider interface, Anthropic and OpenAI
│   ├── tools.py           tool schemas and dispatch
│   ├── prompts.py         system prompt
│   ├── orchestrator.py    tool loop, degraded fallback
│   └── history.py         bounded conversation store
├── routers/               orders, query, health
├── ratelimit.py           fixed-window limiter
└── middleware.py          request id, JSON logging
seed/
├── generators.py          220 bulk orders, seeded RNG
├── scenarios.py           7 hand-built scenarios at fixed ids
└── seed.py                idempotent entry point
static/index.html          operator console, no build step
```

The seed is idempotent. Running it twice produces identical counts
(`orders=227 payments=201 events=437`) because the RNG is seeded.
