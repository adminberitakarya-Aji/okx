# Exchange Adapter Specification (Multi-Exchange)

Version: 2.0

Status: Foundation + Multi-Exchange (OKX, Binance, Bybit)

> **History:** This document was originally `OKX_EXCHANGE_ADAPTER_SPEC.md` (v1.0, OKX-only).
> Renamed and extended in v2.0 to cover the multi-exchange adapter architecture.

## 1. Purpose

`EXCHANGE_ADAPTER_SPEC.md` defines the provider-agnostic adapter contract connecting the AI Trading Grid system to supported exchanges: **OKX, Binance, Bybit**.

Each adapter isolates exchange-specific API semantics from the provider-independent strategy core. All adapters implement the `ExchangeAdapter` ABC defined in `domain/exchange/interface.py`.

```text
CORE
  ↓
EXCHANGE PORT (ExchangeAdapter ABC)
  ↓
ExchangeAdapterFactory
  ├── OKX ADAPTER     → OKX (REST + WebSocket)
  ├── BINANCE ADAPTER → Binance (REST + WebSocket)
  └── BYBIT ADAPTER   → Bybit (REST + WebSocket)
```

### Supported Exchanges

| Exchange | Auth | Demo/Testnet | Symbol Format |
|---|---|---|---|
| OKX | HMAC-SHA256 + Passphrase | `x-simulated-trading: 1` | `BTC-USDT` |
| Binance | HMAC-SHA256 | Spot Testnet (`testnet.binance.vision`) | `BTCUSDT` |
| Bybit | HMAC-SHA256 | Testnet (`api-testnet.bybit.com`) | `BTCUSDT` |

All market identifiers are normalized to the domain format (`BTC-USDT`) at the interface boundary. Concrete adapters convert to/from the exchange's native format via `infrastructure/exchange/symbols.py`.

## 2. Responsibilities

The adapter handles:

- Authentication
- Market data
- Historical data
- Instrument metadata
- Account state
- Balances
- Order submission
- Order state
- Fills
- WebSocket lifecycle
- Rate limits
- Error mapping
- Reconciliation
- Demo/Live environments
- Observability

It does not handle:

- AI decisions
- Market recommendations
- Blueprint generation
- Risk policy
- Grid strategy logic
- ML inference
- Trade approval

## 3. Environment

Supported environments:

```text
DEMO
LIVE
```

Environment must be explicit. No ambiguous automatic selection is permitted.

## 4. Security

Required OKX API permissions:

```text
Read     = ENABLED
Trade    = ENABLED
Withdraw = DISABLED
```

Credentials must be encrypted at rest and never appear in logs, Telegram, datasets, or AI prompts.

IP allowlisting/binding should be enabled where supported.

## 5. Authentication

Internal abstraction:

```text
ExchangeAuthenticator
├── signRequest()
├── authenticateWebSocket()
└── validateCredentialConfiguration()
```

OKX-specific signing and credential semantics remain inside the adapter.

## 6. Provider-Independent Exchange Ports

The application should depend on:

```text
ExchangePort
├── MarketDataPort
├── InstrumentPort
├── AccountPort
├── ExecutionPort
├── OrderQueryPort
└── ReconciliationPort
```

Conceptual methods:

```text
getMarkets()
getTicker()
getCandles()
getOrderBook()
getBalance()
getAccountState()
submitOrder()
cancelOrder()
getOrder()
getOpenOrders()
getOrderHistory()
reconcile()
```

## 7. Market Data

Normalized market entities:

```text
Ticker
OrderBook
MarketTrade
Candle
```

Ticker:

```text
marketId
timestamp
lastPrice
bestBid
bestAsk
midPrice
baseVolume
quoteVolume
```

Order book:

```text
marketId
timestamp
bids[]
asks[]
```

Trade:

```text
tradeId
marketId
timestamp
price
quantity
side
```

Candle:

```text
marketId
timeframe
openTime
closeTime
open
high
low
close
volume
quoteVolume
state
```

Candle state:

```text
CLOSED
IN_PROGRESS
```

This is mandatory for Monthly → Weekly → Daily research.

## 8. Market Identifier Mapping

Core system:

```text
BTC/USDT
```

OKX:

```text
BTC-USDT
```

Mapping remains inside the adapter.

## 9. Historical Data

Interface:

```text
getCandles(
    marketId,
    timeframe,
    startTime,
    endTime,
    limit
)
```

The adapter must:

```text
Normalize timestamps
Sort chronologically
Deduplicate
Validate intervals
Preserve candle state
```

Historical gaps must remain explicit. No synthetic market values are invented by the adapter.

## 10. REST vs WebSocket

General responsibility:

```text
REST
→ snapshots
→ historical data
→ explicit queries
→ recovery
→ reconciliation

WebSocket
→ realtime market streams
→ account updates
→ order updates
```

Realtime market data should primarily use WebSocket.

## 11. WebSocket Components

```text
OKXPublicWebSocket
OKXPrivateWebSocket
```

Public streams:

```text
ticker
trades
order book
candles
```

Private streams:

```text
account
orders
```

Private connections authenticate before private subscriptions.

## 12. Account and Balance

Normalized:

```text
AccountState
├── accountId
├── timestamp
├── totalEquity
├── availableEquity
└── balances[]

Balance
├── asset
├── available
├── frozen
├── total
└── timestamp
```

The current strategy remains Spot-oriented.

## 13. Order Request

Provider-independent:

```text
OrderRequest
├── clientOrderId
├── marketId
├── side
├── executionType
├── quantity
├── quoteAmount
├── price
├── executionPolicy
├── expiry
└── metadata
```

Current strategy:

```text
side = BUY | SELL
executionType = IMMEDIATE
```

The adapter translates the request into the required OKX Spot order parameters.

## 14. Instrument Validation

Before submission:

```text
Strategy Quantity
  ↓
Instrument Rules
  ↓
Normalize
  ↓
Validate
  ↓
OKX Order
```

Validate:

```text
minimum size
maximum size
quantity step
price tick
minimum notional where applicable
```

An invalid request must be rejected before provider submission where possible.

## 15. Order Identity

Every order maintains:

```text
internalOrderId
clientOrderId
providerOrderId
```

The client order ID is used for correlation and safe reconciliation.

## 16. Order State Machine

```text
CREATED
  ↓
SUBMITTED
  ↓
ACKNOWLEDGED
  ↓
PARTIALLY_FILLED
  ↓
FILLED
```

Alternative terminal states:

```text
REJECTED
CANCELED
EXPIRED
UNKNOWN
```

Important:

```text
ACKNOWLEDGED != FILLED
```

## 17. Order Event

```text
OrderEvent
├── eventId
├── timestamp
├── orderId
├── clientOrderId
├── providerOrderId
├── marketId
├── state
├── side
├── requestedQuantity
├── filledQuantity
├── averageFillPrice
├── fee
├── feeAsset
└── rejectionReason
```

## 18. Fill

```text
Fill
├── fillId
├── orderId
├── marketId
├── timestamp
├── side
├── quantity
├── price
├── notional
├── fee
├── feeAsset
└── liquidityRole
```

## 19. Execution Result

```text
ExecutionResult
├── orderId
├── status
├── requestedQuantity
├── filledQuantity
├── averageFillPrice
├── grossNotional
├── fee
├── feeAsset
├── executionTimestamp
└── providerReference
```

Final Net P&L remains the responsibility of the deterministic Execution Economics layer.

## 20. Timeout Safety

Critical rule:

```text
NETWORK TIMEOUT != ORDER FAILED
```

Required flow:

```text
submit
  ↓
timeout
  ↓
query by clientOrderId/provider reference
  ↓
determine actual state
  ↓
reconcile
```

Never blindly resubmit an ambiguous order.

## 21. Rate Limiting

Adapter components:

```text
RateLimiter
RequestQueue
BackoffPolicy
RetryPolicy
```

Safe retry candidates include read/query operations.

Order submission retries require reconciliation first.

## 22. Error Mapping

OKX errors map to domain errors:

```text
AUTHENTICATION_ERROR
RATE_LIMIT_ERROR
INSUFFICIENT_BALANCE
INVALID_ORDER
INVALID_SIZE
INVALID_MARKET
ORDER_REJECTED
NETWORK_ERROR
TIMEOUT
PROVIDER_UNAVAILABLE
UNKNOWN_EXECUTION_STATE
```

Raw provider diagnostics may be retained outside the core domain.

## 23. Connection Manager

WebSocket lifecycle:

```text
connect()
authenticate()
subscribe()
heartbeat()
monitor()
reconnect()
disconnect()
```

States:

```text
DISCONNECTED
CONNECTING
CONNECTED
AUTHENTICATING
AUTHENTICATED
SUBSCRIBED
DEGRADED
RECONNECTING
```

## 24. Reconnection

```text
DISCONNECT
  ↓
RECONNECT
  ↓
REAUTHENTICATE
  ↓
RESUBSCRIBE
  ↓
REST RECONCILIATION
  ↓
RESUME
```

The system must assume events may have been missed.

## 25. Reconciliation

Required operations:

```text
reconcileAccount()
reconcileOrders()
reconcileBalances()
```

Comparison:

```text
Internal State
      vs
OKX State
```

Mismatch produces:

```text
RECONCILIATION_REQUIRED
```

and must not be silently ignored.

## 26. Startup Recovery

```text
START
 ↓
Load Local State
 ↓
Connect OKX
 ↓
Authenticate
 ↓
Account Snapshot
 ↓
Open Orders
 ↓
Recent Order State
 ↓
Reconcile
 ↓
Policy Check
 ↓
READY
```

Live execution is disabled until required reconciliation passes.

## 27. Demo and Live Safety

Demo must be explicit:

```text
environment = DEMO
```

Live must require explicit activation and checks for:

```text
environment
API permissions
account identity
instrument validity
risk policy
```

Demo and Live credentials are isolated.

## 28. No Withdrawal

The adapter must not expose withdrawal capability.

There is no:

```text
withdraw()
```

port for this system.

## 29. Market Data Flow

```text
OKX WebSocket
  ↓
Parser
  ↓
OKX Mapper
  ↓
Normalized Market Event
  ↓
Event Bus
  ↓
Market State / Research
```

## 30. Historical Data Flow

```text
AI Research
  ↓
HistoricalMarketDataPort
  ↓
OKX REST
  ↓
Normalizer
  ↓
Dataset / Simulator
```

## 31. Execution Flow

```text
Grid Engine
  ↓
Execution Engine
  ↓
ImmediateExecutionRequest
  ↓
ExchangePort
  ↓
OKX Adapter
  ↓
Instrument Validation
  ↓
Order Mapping
  ↓
OKX
  ↓
Order Event
  ↓
Execution State
```

## 32. Telegram Boundary

Telegram must never call OKX directly.

Correct:

```text
Telegram
  ↓
Application / Control API
  ↓
Strategy / Risk / Execution
  ↓
ExchangePort
  ↓
OKX Adapter
  ↓
OKX
```

## 33. Execution Economics Boundary

The adapter exposes normalized execution facts:

```text
reference bid/ask
execution price
filled quantity
fee
timestamp
```

It does not decide:

```text
profitability
minimum profitable exit
grid viability
```

Those remain deterministic Execution Economics responsibilities.

## 34. Versioning

Simulation/trading behavior must identify:

```text
adapter_version
api_contract_version
execution_model_version
```

A provider-specific mapping change should produce a new adapter version.

## 35. Observability

Metrics:

```text
REST request count
REST latency
REST error rate
WebSocket reconnect count
WebSocket message rate
order submission latency
order acknowledgement latency
fill latency
order rejection rate
reconciliation mismatch count
rate-limit events
```

Useful timestamps:

```text
execution_requested_at
request_sent_at
provider_ack_at
first_fill_at
final_fill_at
```

## 36. Logging

May log:

```text
request ID
endpoint
latency
status
provider order ID
error code
connection state
reconciliation result
```

Never log:

```text
API secret
passphrase
raw credentials
authentication signatures
```

## 37. Adapter Package Structure

Recommended:

```text
infrastructure/
└── exchanges/
    └── okx/
        ├── authentication/
        ├── rest/
        │   ├── public/
        │   └── private/
        ├── websocket/
        │   ├── public/
        │   └── private/
        ├── mappers/
        ├── models/
        ├── errors/
        ├── rate_limit/
        ├── reconciliation/
        ├── environment/
        └── OKXExchangeAdapter
```

## 38. Testing

Required:

```text
Unit Tests
Integration Tests
Demo Trading Tests
Reconciliation Tests
Failure Recovery Tests
Exchange Contract Tests
```

Test at minimum:

```text
mapping
validation
authentication
state transitions
market data
account state
order lifecycle
partial fills
timeouts
reconnect
reconciliation
rate limits
error mapping
```

## 39. Provider Independence

Application code calls:

```text
ExchangePort
```

not:

```text
OKXExchangeAdapter
```

Future adapters can implement the same contracts without changing the Grid Strategy.

## 40. Non-Negotiable Rules

1. OKX-specific API details stay inside the adapter.
2. Core strategy never calls OKX directly.
3. ExchangePort remains provider-independent.
4. Read + Trade permissions are sufficient.
5. Withdraw is disabled and not exposed.
6. Demo and Live are explicit and isolated.
7. WebSocket is preferred for realtime streams.
8. REST is used for history, snapshots, queries, and reconciliation.
9. Acknowledged does not mean filled.
10. Timeout does not mean order failure.
11. Ambiguous submissions must be reconciled before retry.
12. WebSocket reconnect requires reconciliation.
13. Instrument rules are applied before order submission.
14. Internal/provider order IDs are preserved.
15. Execution Economics remains outside the adapter.
16. Credentials never enter AI, Telegram, logs, or datasets.
17. Provider errors map to domain errors.
18. Live trading requires startup reconciliation and policy checks.
19. The adapter must be replaceable without changing strategy logic.
20. The adapter does not make trading decisions.

## 41. Final Definition

An `EXCHANGE_ADAPTER` (OKX, Binance, or Bybit) is:

> **The provider-specific infrastructure layer that translates the Trading Grid system's normalized market, account, and immediate-execution contracts into exchange-specific REST/WebSocket operations while isolating authentication, instrument rules, order semantics, provider errors, connection handling, rate limits, and state reconciliation from the strategy and AI layers.**

Final boundary:

```text
AI
 ↓
Strategy
 ↓
Deterministic Core
 ↓
Execution Engine
 ↓
Exchange Port (ExchangeAdapter ABC)
 ↓
ExchangeAdapterFactory
 ↓
OKX Adapter | Binance Adapter | Bybit Adapter
 ↓
OKX | Binance | Bybit
```
