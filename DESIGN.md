# DESIGN

## The problem as I read it

The brief's three examples are not three variations of a lookup. One of them is
different in kind:

- "What's the payment status for order #4521?" — a lookup.
- "Give me a full status summary for order #2231" — an aggregation.
- "Customer says they've paid for order #1289 but delivery isn't scheduled" —
  **a reconciliation.** Three systems disagree, and the answer is not a status,
  it is a judgement about which system is wrong.

I built for the third one. The other two fall out of it for free. A design that
targets the lookup and hopes the reconciliation emerges from a good prompt gets
the easy cases right and the important case non-deterministically.

That framing decides everything below.

---

## Architecture

```
         natural language
                │
                ▼
   ┌─────────────────────────┐
   │  LLM #1  intent         │   question ──► tool calls
   └────────────┬────────────┘
                ▼
   ┌─────────────────────────┐
   │  DETERMINISTIC PYTHON   │
   │                         │
   │  repository.py          │   ORM ──► OrderSnapshot (frozen, no IO)
   │       │                 │
   │       ▼                 │
   │  rules/engine.py        │   snapshot ──► Discrepancy[]
   │  9 pure rule functions  │
   └────────────┬────────────┘
                ▼
   ┌─────────────────────────┐
   │  LLM #2  synthesis      │   findings ──► prose, evidence cited
   └────────────┬────────────┘
                ▼
      answer + tools_called + facts_used
```

Both LLM boxes are the same model in the same tool-calling loop. They are drawn
separately because the two jobs are different, and neither of them is
*deciding anything*.

---

## The central decision: the model never judges

**A discrepancy exists if and only if a pure Python function says so.**

The alternative — hand the model the rows and ask "is anything wrong here?" —
fails on four counts:

1. **Not testable.** You cannot unit-test a prompt. You can unit-test
   `payment_reconciliation_lag(snapshot) -> Discrepancy | None`. There are 30 such
   tests and they run in 0.02 seconds with the database stopped.
2. **Not deterministic.** The same order must produce the same finding on every
   call. An operations team cannot act on advice that varies run to run.
3. **Not auditable.** `run_discrepancy_check` returns structured evidence with
   table names, row ids and timestamps. "The model noticed something" is not
   evidence.
4. **Not degradable.** Because judgement lives in Python, the service still
   answers correctly when the model is unavailable. If judgement lived in the
   prompt, an outage would be a total outage.

The cost is real and I will name it: nine hand-written rules cover nine known
failure shapes. A tenth failure shape produces `clean: true` and the model will
not invent it, because it is explicitly forbidden from doing so. The system is
deliberately blind to the unknown-unknown in exchange for being right and
provable about the known-known. For money movement, that is the correct trade.
For an exploratory analytics tool it would be the wrong one.

### The rules

| Code | Severity | Condition |
| --- | --- | --- |
| `PAYMENT_RECONCILIATION_LAG` | CRITICAL | cleared ≥ total, order still `CREATED`/`PENDING_PAYMENT`, latest clearing payment older than 30 min |
| `DUPLICATE_PAYMENT_DETECTED` | CRITICAL | two consecutive cleared non-refund payments, identical amount, within 120s |
| `ORPHAN_UTR` | CRITICAL | a `FAILED` payment carries a bank UTR |
| `REFUND_ON_DELIVERED_ORDER` | CRITICAL | order `DELIVERED` with a refund movement |
| `DELIVERY_NOT_SCHEDULED_POST_CONFIRM` | CRITICAL | confirmed >24h ago, delivery still `NOT_SCHEDULED` |
| `WEBHOOK_MISSING` | WARNING | webhook events fewer than cleared payments |
| `PARTIAL_PAYMENT_OUTSTANDING` | WARNING | `0 < settled < total` |
| `DELIVERY_BLOCKED_WITH_REASON` | WARNING | delivery `BLOCKED` |
| `REFUND_IN_FLIGHT` | INFO | a refund is `REFUND_PENDING` |

Rules compose. Order 1289 fires `PAYMENT_RECONCILIATION_LAG` and
`WEBHOOK_MISSING` together, and the synthesis layer presents them as one story:
the money cleared, the callback never arrived, so the order never advanced and
delivery never got scheduled. Two codes, one causal chain.

---

## Data model

Six tables: `customers`, `vehicles`, `orders`, `payments`, `deliveries`,
`order_events`.

### `CAPTURED` and `SETTLED` are separate payment states

This is the load-bearing modelling decision and the entire assignment rests on it.

- `CAPTURED` — money has left the customer's account. Our ledger has not
  reconciled it.
- `SETTLED` — reconciled.

The gap between those two states is where almost every real payment
contradiction lives. Collapse them into a single `PAID` and order 1289 becomes
inexpressible: there is no way to represent "the customer is right and we are
wrong". A `CAPTURED` payment has `settled_at IS NULL` by definition, which is why
`PAYMENT_RECONCILIATION_LAG` keys off `initiated_at` rather than `settled_at`.

### `order_events` is append-only

Six sources of truth for one order, so the timeline is reconstructed rather than
stored as a status field. `source_system` records which of `ORDER_SVC`,
`PAYMENT_GATEWAY`, `LOGISTICS` or `CRM` emitted each event.

Two payoffs: "full status summary" becomes a genuine narrative instead of a flat
status dump, and `WEBHOOK_MISSING` becomes expressible as the *absence* of an
event. A mutable status column cannot represent something that never happened.

For order 1289 the whole bug is four lines:

```
2026-09-10T23:27:50  ORDER_SVC        ORDER_CREATED
2026-09-12T20:23:50  PAYMENT_GATEWAY  PAYMENT_INITIATED
2026-09-12T20:27:50  PAYMENT_GATEWAY  PAYMENT_CAPTURED
2026-09-12T22:52:50  CRM              CUSTOMER_COMPLAINT
```

No `PAYMENT_WEBHOOK_RECEIVED` between the capture and the complaint.

### Money is `NUMERIC(12,2)`, never float

Non-negotiable in a payments schema. Enum values are enforced with `CHECK`
constraints so the database rejects invalid states regardless of application
bugs.

---

## Snapshots: why rules do no IO

`repository.py` converts ORM objects into `OrderSnapshot`, a tree of frozen
dataclasses with no SQLAlchemy in it. Rules take that snapshot and return
findings.

Measured: **6 queries to build a snapshot** (root select plus `selectinload` on
five relations, a fixed cost, not N+1) and **0 queries during `run_rules`**.

`as_of` is a field on the snapshot, not `datetime.now()` inside a rule. Every
time-windowed rule reads `snapshot.as_of`. Without this, the 30-minute
reconciliation window and the 24-hour scheduling window would be untestable and
flaky. It is the difference between a test suite that passes today and one that
still passes next week.

---

## The tool loop

Six read-only tools: `lookup_order`, `get_payment_history`,
`get_delivery_status`, `get_order_timeline`, `run_discrepancy_check`,
`find_orders_by_customer`.

The loop is capped at 3 iterations. On every exit path that is not a normal
answer — provider timeout, provider 5xx, no key configured, cap exceeded — the
service returns `200` with `degraded: true` and the raw findings. `/query` has no
path that raises to the client. An operations tool that 500s when the model is
slow is worse than no tool, because the operator has already told the customer to
hold.

This guarantee was not free. A clean-clone rehearsal exposed a case where it did
not hold: provider construction caught only `ProviderError`, so a missing SDK or
any other constructor failure propagated as a 500. Provider initialisation now
converts every failure into a degraded response, and three regression tests
inject a missing module and an arbitrary `RuntimeError` to keep it that way.

Tool errors are fed back rather than swallowed. A malformed argument produces
`{"is_error": true, "content": {"error": "order_id must be an integer, received 'banana'"}}`
and the model can correct inside the same cap. An unknown order returns
`found: false` rather than raising, because a typo is the most common operator
input and it should not burn an iteration on an exception path.

---

## Read-only is structural, not prompted

The strongest security property here is not the system prompt. It is that **no
write path exists**.

`execute_tool` resolves the tool name against a fixed dispatch dict and raises on
anything else. There is no SQL-execution tool, no update tool, no refund tool.
Three tests enforce this:

- iterate the live dispatch table and assert no tool name begins with `update`,
  `delete`, `insert`, `mark`, `set`, `create` or `refund`, so adding a write tool
  later breaks the build
- five fabricated write tool names (`mark_refunded`, `update_order`,
  `delete_order`, `set_status`, `sql`) all rejected before touching the database
- a hostile session including a direct prompt injection and a `DROP TABLE`
  payload leaves row counts identical

**Even a complete behavioural failure of the model cannot mutate data.** That is
a claim that survives probing in a way "we handle prompt injection" does not.

The prompt layer adds defence in depth: tool output is declared to be data rather
than instructions, and the model is told it is read-only. But the guarantee is
structural.

SQL injection is proven rather than asserted. `find_orders_by_customer` is the
only free-text path into a query; five payloads are tested against both its
parameters, plus an assertion that every table still has rows afterwards.

---

## Caching: deliberately omitted

I profiled before deciding. Snapshot construction is 6 queries. `/query` latency
is dominated by the model round trip, typically 3 to 8 seconds. Caching the
snapshot optimises the millisecond layer and leaves the second layer untouched.
It is the wrong layer.

It is also actively risky here. This system exists to surface *changing,
inconsistent* state. A cached snapshot means an operator can be shown a
discrepancy that was reconciled two minutes ago. Stale data in a reconciliation
tool is not a performance trade-off, it is a correctness bug, and the blast
radius is a wrongly issued refund.

The right cache, if throughput demanded one, is on the **LLM response**, keyed on
the query plus a hash of the order's current state. That attacks the real cost
and invalidates correctly when the order changes.

---

## Auditability as a product decision

`/query` returns `tools_called` and `facts_used` alongside the prose:

```json
"facts_used": [
  "payments.id=193.status=CAPTURED",
  "payments.id=193.gateway_ref=pay_Qm3v7Lp42c",
  "orders.id=1289.status=PENDING_PAYMENT"
]
```

An operator is about to tell a customer their money is safe. They need to see
what that rests on. It also makes the system falsifiable: call
`/orders/1289/diagnose` directly and compare. Any claim in the prose that is not
in `facts_used` is embellishment.

The console surfaces this as an evidence ledger under each finding, in monospace,
because `pay_Zk7p3Cw21g` and `pay_Zk7p3Cw21h` are two different payments on order
5108 and an agent mid-call must distinguish them at a glance.

---

## Seed data

220 bulk orders with a realistic status distribution, plus 7 hand-built scenarios
at fixed ids so every demo query reproduces on a fresh clone. The RNG is seeded,
so the seed is idempotent: two runs produce `orders=227 payments=201 events=437`
both times.

The contradictions are deliberate. Order 1289's missing
`PAYMENT_WEBHOOK_RECEIVED` event is not an oversight in the seed, it is the bug
being simulated.

Two scenarios are healthy on purpose. A reconciliation engine that flags
everything is worthless, so 4521 and 2231 are the false-positive guard, and the
integration tests assert **set equality** on discrepancy codes rather than
membership, so an over-firing rule fails the build.

---

## Testing

130 tests.

| Suite | Tests | Database |
| --- | --- | --- |
| rules | 30 | not required |
| repository | 13 | required |
| orchestrator | 28 | required |
| adversarial | 59 | required |

The rules suite runs with the database stopped in roughly 0.02 seconds. That is
the architecture's canary: the day it needs a database, a rule has started doing
IO.

The orchestrator suite uses a scripted stub provider that replays canned
responses, so the tool loop, the iteration cap, error recovery and the degraded
fallback are all tested deterministically with no API key and no cost.

---

## What I would do next

**Fix the class of bug, not the instance.** Order 1289's missing webhook is a
symptom. The real fix is webhook idempotency keys plus a transactional outbox on
the payment service, so a dropped callback is retried automatically instead of
surfacing as a customer complaint three hours later. This service is a very good
detector of a problem that should not reach production.

**Rule versioning.** Thresholds (30 min, 24h, 120s) are module constants. In
production they belong in configuration, with findings stamped with the rule
version that produced them, so an audit can reconstruct why an order was flagged
last quarter under different thresholds.

**Distributed state.** The rate limiter and conversation store are per-process
and in-memory. Two replicas means two independent limits. Both belong in Redis.

**Response caching** keyed on query plus order-state hash, as above.

**Read replicas** for the diagnose path once order volume makes the 6-query
snapshot load matter.

---

## Known limitations

Stated plainly, because a reviewer finding them is worse than me naming them.

- **Nine rules cover nine known failure shapes.** A tenth is not detected.
- **`REFUND_ON_DELIVERED_ORDER` has unit coverage but no seeded scenario**, so it
  is never exercised end to end.
- **The rate limiter uses a fixed window**, which permits a 2x burst across a
  window boundary. A sliding window or token bucket fixes it; this is a cost
  control rather than a correctness control, so the simpler thing was chosen.
- **Rate limiter and conversation store are per-process and in-memory.** Lost on
  restart, not shared across replicas.
- **Conversation history stores prose turns only, not tool results.** Pairing
  `tool_use_id` across requests would grow context without bound. Follow-ups that
  reference specific earlier tool output may not resolve.
- **`x-forwarded-for` is trusted as sent.** Correct behind a proxy, spoofable if
  exposed directly.
- **No authentication on any endpoint.** Deliberate for a take-home, unacceptable
  in production.
- **No pagination.** Fine at 227 orders, not at 2.27 million.
- **`max_tokens` is 1500.** A very long timeline summary could truncate.
- **`extract_order_ids` is a regex** used only on the degraded path. It can match
  a 4-digit number that is not an order id, which then reports "not found".
- **The Anthropic provider is the tested path.** The OpenAI provider implements
  the same interface but has not been exercised end to end.
