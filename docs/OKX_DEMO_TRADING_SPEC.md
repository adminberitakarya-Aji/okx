# OKX DEMO TRADING SPECIFICATION

---

# 1. Purpose

This document defines how the AI Trading Grid system uses OKX Demo Trading as a safe, isolated environment for development, testing, validation, and operational rehearsal before any live trading activity.

Demo Trading is the **mandatory intermediate environment** between research/simulation and live production trading.

---

# 2. Core Principle

```text
Research / Simulation
        ↓
Demo Trading (OKX Demo / Binance Testnet / Bybit Testnet)
        ↓
Validation & Rehearsal
        ↓
Beta Multi-Tenant Validation (Phase 5)
        ↓
Live Trading (Phase 6)
```

Demo Trading:

- Uses OKX's simulated trading environment
- Does NOT risk real funds
- Mirrors live API behavior as closely as possible
- Is fully isolated from live trading
- Is required before any live trading approval

---

# 3. OKX Demo Trading Overview

OKX provides a Demo Trading environment that:

```text
- Uses the same API endpoints as live trading
- Requires a special header: x-simulated-trading: 1
- Uses separate demo API keys
- Provides simulated funds (demo balance)
- Executes orders against simulated liquidity
```

## Key Difference from Live

```text
Live:
  REST base: https://www.okx.com
  No special header

Demo:
  REST base: https://www.okx.com
  Header: x-simulated-trading: 1
```

The adapter must inject this header for all demo requests.

---

# 4. Environment Configuration

## Demo Environment Declaration

```text
environment: DEMO
okx_mode: demo
simulated_trading_header: true
```

## Demo API Credentials

```text
- Separate API key created in OKX Demo Trading
- Separate secret and passphrase
- Stored in Secret Manager under demo-specific path
- Never mixed with live credentials
```

## Demo Account Setup

```text
1. Create OKX account (if not exists)
2. Enable Demo Trading in OKX dashboard
3. Create Demo API key with Read + Trade permissions
4. Disable Withdraw permission (even in demo)
5. Fund demo account with simulated USDT
6. Store credentials in Secret Manager
```

---

# 5. Demo Adapter Behavior

The OKX Adapter must support demo mode transparently.

```text
ExchangePort
     ↓
OKXExchangeAdapter
     ↓
Environment Check
     ├── DEMO → inject x-simulated-trading: 1
     └── LIVE → no header
```

The rest of the application stack is **environment-agnostic**.

The adapter is the **only** component that knows whether it is talking to demo or live.

---

# 6. Demo Market Data

## Important Limitation

```text
OKX Demo Trading market data may differ from live market data.
```

Specifically:

```text
- Order book depth may be simulated
- Trade volume may be lower
- Price may lag live market
- Liquidity may not reflect real conditions
```

## Implication

```text
- Demo execution prices may differ from live
- Slippage in demo may not reflect live slippage
- Fill rates in demo may be more optimistic
- Demo results are NOT a guarantee of live performance
```

## Recommendation

```text
- Use live market data for research and ML features
- Use demo trading for execution flow validation
- Do NOT use demo execution results as ML training labels
- Treat demo P&L as operational validation, not economic validation
```

---

# 7. What Demo Trading Validates

Demo Trading is used to validate:

```text
1. API connectivity and authentication
2. Order submission flow
3. Order lifecycle (submit → ack → fill → settle)
4. WebSocket connection and reconnection
5. Account balance and position tracking
6. Grid engine state machine
7. Section activation and deactivation
8. Capital allocation logic
9. Error handling and recovery
10. Reconciliation after disconnect
11. Telegram notification flow
12. Emergency stop procedure
13. Pause / resume behavior
14. Multi-grid concurrent operation
```

---

# 8. What Demo Trading Does NOT Validate

Demo Trading does NOT validate:

```text
1. Real market liquidity
2. Real slippage
3. Real spread under stress
4. Real execution economics
5. Real P&L outcomes
6. Strategy profitability
7. ML model accuracy
8. Market regime prediction
```

These require live trading with real funds.

---

# 9. Demo Trading Workflow

```text
1. System startup in DEMO mode
2. Connect to OKX Demo API
3. Verify demo account balance
4. Run startup reconciliation
5. Receive blueprint (from research or manual)
6. Validate blueprint
7. Start grid in demo
8. Monitor order flow
9. Validate grid behavior
10. Collect demo metrics
11. Stop grid
12. Generate demo report
```

---

# 10. Demo Grid Lifecycle

```text
DEMO_GRID_CREATED
     ↓
DEMO_GRID_RUNNING
     ↓
DEMO_GRID_PAUSED (optional)
     ↓
DEMO_GRID_RESUMED (optional)
     ↓
DEMO_GRID_STOPPED
     ↓
DEMO_GRID_COMPLETED
```

All lifecycle events are logged and audited.

---

# 11. Demo Data Storage

Demo trading data is stored separately from live data.

```text
demo_data/
├── orders/
├── fills/
├── grid_states/
├── account_snapshots/
├── metrics/
└── reports/
```

Demo data:

```text
- Is NOT used for ML training
- Is NOT mixed with live data
- May be used for operational analysis
- May be purged after validation period
```

---

# 12. Demo Metrics

Track operational metrics during demo trading:

```text
- Order submission latency
- Order acknowledgement rate
- Fill rate
- WebSocket reconnect count
- Reconciliation mismatch count
- Grid state transition count
- Error rate by category
- API rate limit hits
```

These metrics validate **operational readiness**, not strategy performance.

---

# 13. Demo-to-Live Transition Criteria

Before transitioning from demo to live, ALL criteria must be met:

```text
☑ Demo grid ran for minimum defined period (e.g., 7 days)
☑ Zero reconciliation mismatches
☑ Zero unhandled errors
☑ WebSocket reconnection tested and passed
☑ Emergency stop tested and passed
☑ Pause/resume tested and passed
☑ All order lifecycle states observed
☑ Telegram notifications working
☑ Audit logging complete
☑ Demo metrics within acceptable thresholds
☑ Security review passed
☑ Beta multi-tenant validation passed (Phase 5)
☑ Live trading approval granted
```

---

# 14. Demo-to-Live Checklist

```text
PRE-LIVE CHECKLIST

Environment:
☑ Live API keys created (Read + Trade only)
☑ Live keys stored in Secret Manager
☑ Live environment configuration verified
☑ Demo and Live credentials are separate

System:
☑ All demo validation criteria met
☑ Reconciliation clean
☑ Risk limits configured for live
☑ Capital allocation approved
☑ Emergency stop procedure tested

Approval:
☑ Live trading approval requested
☑ Live trading approval granted by authorized user
☑ Approval recorded in audit log

Monitoring:
☑ Live monitoring dashboard ready
☑ Alert thresholds configured
☑ Notification routing verified
```

---

# 15. Demo Environment Monitoring

```text
Demo Health Dashboard:
├── OKX Demo API connectivity
├── WebSocket status
├── Active demo grids
├── Demo order flow
├── Demo error rate
├── Demo reconciliation status
└── Demo metrics summary
```

---

# 16. Demo Trading Limitations

Operators must understand:

```text
1. Demo fills may be faster than live
2. Demo liquidity may be deeper than live
3. Demo prices may not reflect real market
4. Demo P&L is not real P&L
5. Demo success does not guarantee live success
6. Demo is for operational validation only
```

---

# 17. Demo Trading Policies

```text
- Demo trading is allowed for all authorized users (LEVEL 2+)
- Demo trading does not require live approval
- Demo grids can be started/stopped freely
- Demo data is isolated from live data
- Demo credentials are never used for live
- Demo environment is clearly labeled in all UI
```

---

# 18. Demo vs Live Comparison

| Aspect | DEMO | LIVE |
|---|---|---|
| Funds | Simulated | Real |
| API Key | Demo key | Live key |
| Header | x-simulated-trading: 1 | None |
| Market Data | May be simulated | Real |
| Liquidity | May differ | Real |
| P&L | Not real | Real |
| Risk | None | Real |
| Approval | LEVEL 2+ | LEVEL 3+ + approval |
| ML Training | Not used | May be used (with caution) |

---

# 19. Demo Trading in Research Pipeline

```text
AI Research (historical simulation)
     ↓
Candidate Blueprint
     ↓
Demo Trading (operational validation)
     ↓
Validation Report
     ↓
Live Trading Approval
     ↓
Live Trading
```

Demo trading is the **bridge** between research and live.

It validates that the system can execute the blueprint correctly, not that the blueprint is profitable.

---

# 20. Demo Failure Handling

If demo trading reveals issues:

```text
1. Stop demo grid
2. Log issue with full context
3. Analyze root cause
4. Fix issue
5. Re-run demo validation
6. Do NOT proceed to live until resolved
```

Demo failures are **learning opportunities**, not blockers.

---

# 21. Demo Reporting

After demo validation period, generate report:

```text
Demo Validation Report
├── Period: start → end
├── Grids tested: count
├── Orders submitted: count
├── Orders filled: count
├── Errors: count by category
├── Reconciliation: clean / issues
├── WebSocket reconnects: count
├── Emergency stops: count
├── Metrics summary
├── Issues found
├── Recommendations
└── Ready for live: YES / NO
```

---

# 22. Non-Negotiable Rules

1. Demo trading uses separate API keys from live.
2. Demo trading requires x-simulated-trading: 1 header.
3. Demo and live environments are fully isolated.
4. Demo market data may differ from live; treat accordingly.
5. Demo execution results are NOT used for ML training.
6. Demo P&L is operational validation, not economic validation.
7. Demo-to-live transition requires explicit checklist completion.
8. Live trading requires explicit approval after demo validation.
9. Demo data is stored separately from live data.
10. Demo environment is clearly labeled in all interfaces.
11. Demo credentials are never used for live trading.
12. Demo trading does not require live-level approval.
13. Demo failures must be resolved before live transition.
14. Demo validation report is generated before live approval.
15. The adapter is the only component aware of demo vs live.

---

# 23. Final Definition

OKX Demo Trading is:

> **The isolated, simulated trading environment used to validate the operational correctness of the AI Trading Grid system — API connectivity, order lifecycle, grid state machine, reconciliation, error handling, and notification flow — before any live trading activity, without risking real funds and without contaminating research data.**

Demo trading boundary:

```text
Research / Simulation
        ↓
DEMO TRADING (OKX Demo / Binance Testnet / Bybit Testnet)
        ↓
Operational Validation
        ↓
Demo Report
        ↓
Beta Multi-Tenant Validation (Phase 5)
        ↓
Live Approval
        ↓
LIVE TRADING (Phase 6)
```

Demo trading proves the system works.

It does not prove the strategy profits.

That distinction is critical.