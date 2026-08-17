# Application Control API Specification

Version: 1.0

Status: Foundation

Purpose:

`APPLICATION_CONTROL_API_SPEC.md` defines the provider-independent application/control layer between user interfaces, automation clients, AI systems, strategy engines, risk systems, and exchange adapters.

The Application Control API is the central application boundary.

It provides controlled access to:

```text
AI Research
Realtime AI
Market Recommendation
Grid Blueprint
Simulation
Risk
Grid Runtime
Account
Orders
Positions
P&L
Approvals
System Controls
```

It does NOT expose OKX directly to clients.

---

# 1. Core Principle

The architecture is:

```text
USER / CLIENT
      |
      v
APPLICATION CONTROL API
      |
      +------------------+
      |                  |
      v                  v
USE CASES           CONTROL / POLICY
      |
      +-----------------------------+
      |             |               |
      v             v               v
AI / RESEARCH   GRID / RISK    ACCOUNT / EXECUTION
                                      |
                                      v
                               EXCHANGE PORT
                                      |
                                      v
                                OKX ADAPTER
```

Clients such as:

```text
Telegram
Web UI
Internal CLI
Admin tools
Automation
```

must call the Application Control API.

They must not call:

```text
OKX API
Grid Engine internals
Risk Engine internals
AI provider APIs
```

directly.

---

# 2. Responsibilities

The Application Control API is responsible for:

```text
Authentication boundary
Authorization boundary
Command routing
Use-case invocation
Query routing
Approval workflow
Operation state
Idempotency
Audit trail
Response normalization
Error normalization
Observability
```

It is NOT responsible for:

```text
Grid mathematical calculations
ML inference implementation
Market indicator calculations
Exchange protocol implementation
Raw OKX authentication
Telegram UI logic
```

Those remain in their respective modules.

---

# 3. API Types

The application boundary is divided into:

```text
QUERY
COMMAND
APPROVAL
CONTROL
EVENT
```

---

# 4. Query

Queries read state without intentionally changing business state.

Examples:

```text
Get Research Universe
Get Market Recommendation
Get Market Detail
Get Blueprint
Get Simulation Result
Get Grid Status
Get Account
Get Balances
Get Orders
Get Positions
Get P&L
Get Risk State
Get System Status
```

---

# 5. Command

Commands request a state-changing operation.

Examples:

```text
Create Research Run
Create Blueprint
Run Simulation
Approve Blueprint
Start Grid
Pause Grid
Resume Grid
Stop Grid
Cancel Order
Refresh Research
```

A command must produce:

```text
Command ID
Operation ID
Initial Status
```

---

# 6. Approval

Approval is a separate application concept.

Examples:

```text
Approve Research Recommendation
Approve Blueprint
Approve Live Grid Start
Approve High-Risk Operation
```

Approval should never be hidden inside a generic command.

---

# 7. Control Operations

Control operations affect runtime state.

Examples:

```text
START
PAUSE
RESUME
STOP
EMERGENCY_STOP
```

These require stronger authorization than read-only queries.

---

# 8. API Boundary

Conceptual API:

```text
/api/v1
```

Namespaces:

```text
/api/v1/research
/api/v1/markets
/api/v1/blueprints
/api/v1/simulations
/api/v1/grid
/api/v1/account
/api/v1/orders
/api/v1/positions
/api/v1/pnl
/api/v1/risk
/api/v1/approvals
/api/v1/system
```

The exact transport may be HTTP/REST initially.

Internal eventing may use a message/event bus.

---

# 9. Authentication

The API requires an authenticated caller.

Conceptual:

```text
Authentication
      ↓
Identity
      ↓
Authorization
      ↓
Use Case
```

Possible identity:

```text
user_id
service_id
session_id
client_id
```

The API must distinguish:

```text
HUMAN
SERVICE
SYSTEM
```

---

# 10. Authorization

Authorization is policy-based.

Example permissions:

```text
research.read
research.run

market.read

blueprint.read
blueprint.create
blueprint.approve

simulation.run
simulation.read

grid.read
grid.start
grid.pause
grid.resume
grid.stop
grid.emergency_stop

account.read
orders.read
orders.cancel
positions.read
pnl.read

live.execute
live.approve
```

A permission must be checked before command execution.

---

# 11. Environment Awareness

The API must know:

```text
DEMO
LIVE
```

It must never silently route a Demo command to Live.

Every trading-related command should carry or resolve:

```text
environment
```

Example:

```text
environment = DEMO
```

---

# 12. Live Trading Guard

Live trading must require explicit policy validation.

Conceptual:

```text
Live Command
      ↓
Identity
      ↓
Authorization
      ↓
Environment Check
      ↓
Risk Check
      ↓
Approval Policy
      ↓
Execution
```

If any gate fails:

```text
COMMAND_REJECTED
```

---

# 13. Research API

## GET /research/universe

Returns the current eligible Research Universe.

Example:

```text
{
  "universe_type": "OKX_SPOT_TOP_10",
  "snapshot_id": "U-2026-08-15",
  "markets": [...]
}
```

---

## GET /research/market/{marketId}

Returns current Market Research context.

Includes:

```text
market_state
execution_economics
grid_suitability
recommendation
confidence
```

---

## GET /research/recommendations

Returns ranked Market Recommendations.

Example:

```text
1. BTC/USDT
2. ETH/USDT
3. SOL/USDT
...
```

---

## POST /research/runs

Creates a research run.

Request:

```text
{
  "universe": "TOP_10",
  "environment": "DEMO"
}
```

Returns:

```text
research_run_id
operation_id
status
```

Research execution may be asynchronous.

---

# 14. Market API

## GET /markets

Returns normalized markets available to the application.

This is not necessarily the same as the Research Top 10.

The distinction is:

```text
All Eligible Exchange Markets
vs
AI Research Universe
```

The current Research Universe remains Top 10.

---

## GET /markets/{marketId}

Returns:

```text
Market
Instrument
Ticker
Liquidity
Status
```

---

# 15. Blueprint API

## POST /blueprints

Creates a candidate Blueprint.

Input:

```text
market_id
capital
section_count
section_allocation
grid_spacing
section_gap
price_ranges
grid_count
```

The Blueprint service validates:

```text
allocation
uniform spacing
section gap
price ordering
capital constraints
instrument constraints
```

---

## GET /blueprints/{blueprintId}

Returns the normalized Blueprint.

---

## POST /blueprints/{blueprintId}/validate

Runs deterministic Blueprint validation.

Result:

```text
VALID
or
INVALID
```

---

## POST /blueprints/{blueprintId}/simulate

Creates a simulation operation.

Returns:

```text
simulation_run_id
operation_id
status
```

---

# 16. Simulation API

## POST /simulations

Input:

```text
market_id
observation_timestamp
horizon
blueprint_id
environment
```

The Simulation API routes to:

```text
Historical Grid Simulator
```

---

## GET /simulations/{simulationRunId}

Returns:

```text
status
performance
grid_behavior
capital
drawdown
recovery
terminal_condition
```

---

# 17. Grid Runtime API

The runtime API controls a validated Grid instance.

## GET /grid

Returns active Grid runtimes.

---

## GET /grid/{gridId}

Returns:

```text
grid_id
market
environment
status
blueprint
capital
exposure
sections
positions
pnl
risk
```

---

## POST /grid/{gridId}/start

Starts a Grid runtime.

Required gates:

```text
Authentication
Authorization
Environment
Blueprint Validity
Risk Validation
Execution Readiness
Approval Policy
```

---

## POST /grid/{gridId}/pause

Pauses new strategy activity according to runtime policy.

It must not necessarily force-close positions.

---

## POST /grid/{gridId}/resume

Resumes a paused Grid after policy checks.

---

## POST /grid/{gridId}/stop

Stops the Grid according to the configured stop policy.

Stop policy must specify whether:

```text
new entries stop
open positions remain
open positions are closed
```

The API must not assume forced liquidation.

---

## POST /grid/{gridId}/emergency-stop

Emergency operation.

This requires the highest authorization level.

Emergency behavior must be deterministic and preconfigured.

---

# 18. Account API

## GET /account

Returns normalized account state.

---

## GET /account/balances

Returns:

```text
asset
available
frozen
total
```

The Application API does not expose raw API credentials.

---

# 19. Orders API

## GET /orders

Query filters:

```text
market_id
grid_id
status
from
to
environment
```

---

## GET /orders/{orderId}

Returns normalized order state.

---

## POST /orders/{orderId}/cancel

Cancellation is a command and requires authorization.

If the order is already filled:

```text
CANCEL_NOT_ALLOWED
```

The API must not pretend cancellation succeeded.

---

# 20. Positions API

## GET /positions

Returns:

```text
market
asset_quantity
average_cost
current_value
unrealized_pnl
realized_pnl
```

For Grid-specific context:

```text
section
grid_id
exposure
```

may also be included.

---

# 21. P&L API

## GET /pnl

Supports:

```text
current
daily
grid
market
period
```

Core economics must use the canonical Net P&L model.

---

# 22. Risk API

## GET /risk

Returns:

```text
risk_state
capital_state
exposure
drawdown
section_depth
capital_reserve
execution_risk
```

---

## POST /risk/validate

Validates a proposed operation.

Example:

```text
Validate Blueprint
Validate Start
Validate Resume
Validate Live Execution
```

---

# 23. Approval API

## GET /approvals

Returns pending approvals.

---

## POST /approvals/{approvalId}/approve

Approval must contain:

```text
approval_id
approver_id
timestamp
decision
```

---

## POST /approvals/{approvalId}/reject

Explicit rejection.

---

# 24. Approval State Machine

```text
PENDING
  ↓
APPROVED
```

or:

```text
PENDING
  ↓
REJECTED
```

or:

```text
PENDING
  ↓
EXPIRED
```

Approval must be bound to the exact:

```text
operation
blueprint
market
environment
```

being approved.

A generic approval should not be reusable for another operation.

---

# 25. Idempotency

Every state-changing command should support:

```text
idempotency_key
```

This is especially important for:

```text
start
resume
stop
cancel
approve
execute
```

Example:

```text
POST /grid/G-001/start
Idempotency-Key: abc123
```

If the same command arrives twice with the same key, the system returns the existing operation result instead of executing twice.

---

# 26. Operation Model

Long-running commands return an Operation.

```text
Operation
├── operation_id
├── command_type
├── status
├── created_at
├── started_at
├── completed_at
├── initiated_by
├── environment
├── resource_type
├── resource_id
├── error
└── result_reference
```

Statuses:

```text
PENDING
RUNNING
SUCCEEDED
FAILED
CANCELED
REJECTED
EXPIRED
```

---

# 27. Asynchronous Operations

Use asynchronous operations for:

```text
Research Runs
Simulation
Model inference batches
Universe refresh
Large reconciliation
Backfills
```

Immediate commands may return:

```text
202 Accepted
```

with:

```text
operation_id
```

---

# 28. Synchronous Operations

Suitable for:

```text
Read queries
Blueprint validation
Risk validation
Simple account queries
Simple order queries
```

---

# 29. Command Result

Normalized:

```text
CommandResult
├── command_id
├── operation_id
├── status
├── resource_type
├── resource_id
└── result
```

---

# 30. Error Contract

Normalized API error:

```text
ApiError
├── code
├── message
├── category
├── retryable
├── operation_id
└── details
```

Categories:

```text
AUTHENTICATION
AUTHORIZATION
VALIDATION
CONFLICT
NOT_FOUND
RISK
EXECUTION
PROVIDER
TIMEOUT
SYSTEM
```

Provider-specific OKX errors must not leak into public API contracts.

---

# 31. Example Error

```text
{
  "code": "LIVE_EXECUTION_NOT_APPROVED",
  "message": "Live execution requires explicit approval.",
  "category": "AUTHORIZATION",
  "retryable": false,
  "operation_id": "OP-123"
}
```

---

# 32. Event Boundary

The API should publish normalized application events.

Examples:

```text
ResearchCompleted
RecommendationUpdated
BlueprintCreated
BlueprintValidated
SimulationCompleted
GridStarted
GridPaused
GridResumed
GridStopped
OrderSubmitted
OrderFilled
OrderRejected
RiskStateChanged
ReconciliationRequired
```

Events are internal/application events, not raw OKX events.

---

# 33. Event Envelope

```text
EventEnvelope
├── event_id
├── event_type
├── event_version
├── timestamp
├── correlation_id
├── causation_id
├── actor
├── environment
└── payload
```

This supports tracing.

---

# 34. Correlation

One user action may create multiple internal operations.

Example:

```text
Telegram Command
      ↓
Correlation ID
      ↓
Research
      ↓
Recommendation
      ↓
Blueprint
      ↓
Risk
      ↓
Execution
```

All operations should preserve the correlation ID.

---

# 35. Audit Trail

Every state-changing command must create an audit record:

```text
AuditRecord
├── audit_id
├── actor_id
├── actor_type
├── command
├── timestamp
├── resource
├── environment
├── result
├── correlation_id
└── metadata
```

Sensitive credentials are excluded.

---

# 36. Runtime State Query

## GET /system/status

Returns:

```text
environment
api_status
okx_connection
market_data_status
private_ws_status
reconciliation_status
grid_runtime_status
research_status
```

---

# 37. Readiness

The system should expose:

```text
GET /system/readiness
```

Possible:

```text
READY
NOT_READY
DEGRADED
BLOCKED
```

Readiness can depend on:

```text
OKX connectivity
market data
account synchronization
reconciliation
risk engine
required services
```

---

# 38. Trading Readiness

Separate:

```text
System Ready
```

from:

```text
Trading Ready
```

A system may be operational but not allowed to trade.

Conceptually:

```text
System Ready
      +
OKX Ready
      +
Risk Ready
      +
Reconciliation Clean
      +
Approval
      ↓
Trading Ready
```

---

# 39. Market Recommendation Response

Example:

```text
{
  "market_id": "BTC/USDT",
  "rank": 1,
  "recommendation": "HIGH_PRIORITY",
  "suitability_score": 0.91,
  "confidence": 0.88,
  "market_regime": "CORRECTIVE_BULLISH",
  "execution_quality": "HIGH",
  "research_reasons": [...]
}
```

The score must be traceable to underlying research/model outputs.

---

# 40. Blueprint Response

Example:

```text
{
  "blueprint_id": "BP-0042",
  "market_id": "BTC/USDT",
  "section_count": 3,
  "sections": [
    {
      "allocation": 0.30,
      "grid_spacing": 0.01
    },
    {
      "allocation": 0.35,
      "grid_spacing": 0.015
    },
    {
      "allocation": 0.35,
      "grid_spacing": 0.02
    }
  ],
  "section_gaps": [
    0.05,
    0.10
  ],
  "validation_status": "VALID"
}
```

The API returns configuration; it does not claim profitability guarantees.

---

# 41. Grid Runtime Response

Example:

```text
{
  "grid_id": "GRID-001",
  "market_id": "BTC/USDT",
  "environment": "DEMO",
  "status": "RUNNING",
  "section_depth": 2,
  "capital_utilization": 0.56,
  "exposure": ...,
  "unrealized_pnl": ...,
  "realized_pnl": ...
}
```

---

# 42. Command Authorization Levels

Suggested:

```text
LEVEL 0
Read-only

LEVEL 1
Research / Simulation

LEVEL 2
Demo Grid Control

LEVEL 3
Live Grid Control

LEVEL 4
Emergency Control
```

Actual roles can map to these capabilities.

---

# 43. Telegram Compatibility

Telegram Gateway should call this API only.

Examples:

```text
/research
→ GET /research/recommendations

/market BTC
→ GET /research/market/BTC-USDT

/blueprint BTC
→ GET /blueprints/...

/simulate
→ POST /simulations

/status
→ GET /system/status

/pause
→ POST /grid/{id}/pause
```

Telegram itself does not implement these use cases.

---

# 44. UI Independence

A future Web UI should be able to perform the same operations:

```text
Web UI
  ↓
Application Control API
```

without changing business logic.

Likewise:

```text
CLI
  ↓
Application Control API
```

---

# 45. API Security

The API should implement:

```text
Authentication
Authorization
Rate Limiting
Request Validation
Idempotency
Audit Logging
Correlation IDs
Environment Guards
```

Sensitive control endpoints should use stronger authorization.

---

# 46. API Rate Limiting

Separate limits may apply to:

```text
Read
Research
Simulation
Control
Live Operations
```

Live execution commands should have stricter protection than read queries.

---

# 47. Dangerous Operation Protection

Dangerous commands such as:

```text
live start
resume
stop
emergency-stop
```

should require:

```text
authorization
policy validation
idempotency
audit
```

and, where configured:

```text
explicit approval
```

---

# 48. No Direct Exchange Credentials

Client requests NEVER contain:

```text
OKX API Key
OKX Secret
OKX Passphrase
```

The application resolves credentials internally through its secure integration configuration.

---

# 49. No Direct AI Provider Credentials

The same rule applies to AI providers.

Clients do not submit:

```text
LLM API keys
model-provider credentials
```

The application owns provider configuration.

---

# 50. Observability

Application metrics:

```text
request_count
request_latency
error_rate
command_success_rate
authorization_denials
approval_count
operation_duration
reconciliation_events
active_grid_count
```

Distributed tracing should preserve:

```text
request_id
correlation_id
causation_id
operation_id
```

---

# 51. API Versioning

Initial:

```text
/api/v1
```

Breaking API changes require:

```text
/api/v2
```

Internal event schemas also require explicit:

```text
event_version
```

---

# 52. Compatibility Policy

Changes should preserve existing commands where possible.

Breaking changes require:

```text
new API version
migration path
documentation
```

---

# 53. Recommended Application Package Structure

Conceptual:

```text
application/
├── commands/
│   ├── research/
│   ├── blueprint/
│   ├── simulation/
│   ├── grid/
│   ├── approval/
│   └── system/
│
├── queries/
│   ├── research/
│   ├── market/
│   ├── blueprint/
│   ├── simulation/
│   ├── grid/
│   ├── account/
│   ├── orders/
│   ├── positions/
│   ├── pnl/
│   └── risk/
│
├── services/
│   ├── authorization/
│   ├── approval/
│   ├── readiness/
│   └── audit/
│
└── ports/
    ├── exchange/
    ├── ai/
    ├── research/
    ├── grid/
    └── notification/
```

---

# 54. Integration Flow

Full application flow:

```text
USER
  ↓
Telegram / Web / CLI
  ↓
Application Control API
  ↓
Authentication
  ↓
Authorization
  ↓
Use Case
  ↓
Business Services / Engines
  ↓
Risk + Deterministic Validation
  ↓
Execution Engine
  ↓
Exchange Port
  ↓
OKX Adapter
  ↓
OKX
```

Research flow:

```text
Client
  ↓
Application API
  ↓
Research Use Case
  ↓
Top 10 Universe
  ↓
AI Research
  ↓
Market Recommendation
```

Blueprint flow:

```text
Client
  ↓
Application API
  ↓
Blueprint Use Case
  ↓
Realtime AI
  ↓
Blueprint
  ↓
Deterministic Validation
```

---

# 55. Non-Negotiable Rules

1. Clients never call OKX directly.
2. Telegram never contains business logic.
3. Application Control API is provider-independent.
4. Commands are separate from queries.
5. State-changing commands require authorization.
6. Dangerous operations require stronger controls.
7. Live trading requires explicit environment and policy validation.
8. Idempotency is mandatory for state-changing commands.
9. Long-running work uses Operation objects.
10. Provider-specific errors do not leak through public contracts.
11. API credentials never enter client requests.
12. Approval is explicit and bound to the exact operation/environment/blueprint.
13. System readiness and trading readiness remain separate.
14. Audit records are required for state-changing operations.
15. AI does not directly execute provider API calls.
16. Application API does not bypass deterministic risk/economic validation.
17. Emergency controls remain explicit and auditable.
18. API and event schemas are versioned.
19. Correlation IDs must follow multi-step operations.
20. The API is an application boundary, not a second strategy engine.

---

# 56. Final Definition

The Application Control API is:

> **The provider-independent application boundary that converts external user/system requests into authenticated, authorized, auditable use-case operations across AI Research, Realtime AI, Grid, Risk, Account, and Execution services, while preventing clients such as Telegram from directly accessing business engines or exchange providers.**

Final architecture:

```text
                    USERS / SYSTEMS
                    /      |      \
                 Telegram  Web     CLI
                    \       |      /
                     \      |     /
                      ▼     ▼    ▼
                APPLICATION CONTROL API
                         |
              Authentication / Authorization
                         |
                     Use Cases
                         |
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   AI RESEARCH      REALTIME AI       GRID / RISK
        |                |                |
        └────────────────┼────────────────┘
                         ▼
                 DETERMINISTIC CORE
                         |
                  EXECUTION ENGINE
                         |
                   EXCHANGE PORT
                         |
                    OKX ADAPTER
                         |
                        OKX
```
