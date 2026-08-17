# LIVE TRADING SPECIFICATION

---

# 1. Purpose

This document defines the operational requirements, approval workflow, monitoring, incident response, and safety controls for live trading with real funds on supported exchanges (OKX, Binance, Bybit).

Live trading is the **highest-risk operational mode** of the AI Trading Grid system.

---

# 2. Core Principle

```text
Live trading is NEVER the default.
Live trading is NEVER automatic.
Live trading is NEVER unmonitored.
```

Live trading requires:

```text
1. Explicit approval
2. Validated blueprint
3. Clean reconciliation
4. Configured risk limits
5. Active monitoring
6. Emergency controls ready
```

---

# 3. Live Trading Definition

```text
LIVE TRADING = Real funds at risk on exchange Spot market (OKX, Binance, or Bybit)
```

Unlike demo trading:

```text
- Real capital is deployed
- Real orders are submitted
- Real fills occur
- Real P&L is generated
- Real losses are possible
```

---

# 4. Live Trading Prerequisites

Before ANY live trading can occur:

```text
☑ Demo validation completed successfully
☑ Demo validation report generated
☑ Beta multi-tenant validation passed (Phase 5)
☑ Live API keys created and secured
☑ Live environment configured
☑ Risk limits defined and approved
☑ Capital allocation approved
☑ Monitoring dashboard active
☑ Alert thresholds configured
☑ Emergency stop tested
☑ Live trading approval granted
```

---

# 5. Live Trading Approval Workflow

```text
Request Live Trading
        ↓
Pre-Check Validation
        ↓
Approval Request Created
        ↓
Notify Authorized Approver (LEVEL 3+)
        ↓
Approver Reviews:
  - Blueprint details
  - Risk limits
  - Capital allocation
  - Demo validation report
  - Market conditions
        ↓
Approver Decision
  ├── APPROVE → Proceed
  └── REJECT → Stop, log reason
        ↓
Approval Record Created
        ↓
Live Trading Authorized
```

---

# 6. Approval Record

```text
LiveTradingApproval
├── approval_id
├── requested_by
├── approved_by
├── timestamp
├── blueprint_id
├── market_id
├── environment: LIVE
├── capital_allocation
├── risk_limits
├── demo_validation_reference
├── conditions
└── expiry
```

Approval is:

```text
- Bound to specific blueprint
- Bound to specific market
- Bound to specific capital amount
- Time-limited (expiry)
- Revocable
```

---

# 7. Live Environment Configuration

```text
environment: LIVE
exchange_mode: live (per exchange)
simulated_trading_header: false (OKX)
testnet_mode: false (Binance/Bybit)
```

## Live API Credentials

```text
- Separate from demo credentials
- Read + Trade permissions only
- Withdraw DISABLED
- IP whitelist configured
- Stored in Secret Manager (live path)
```

---

# 8. Live Trading Startup Sequence

```text
1. System startup in LIVE mode
2. Load live credentials from Secret Manager
3. Connect to OKX Live API
4. Verify live account balance
5. Run startup reconciliation
6. Verify no open orders from previous session
7. Verify grid state consistency
8. Load approved blueprint
9. Validate blueprint against current market
10. Confirm risk limits active
11. Confirm monitoring active
12. Confirm alerts configured
13. Start live grid
14. Begin continuous monitoring
```

---

# 9. Live Grid Lifecycle

```text
LIVE_GRID_APPROVED
     ↓
LIVE_GRID_CREATED
     ↓
LIVE_GRID_RUNNING
     ↓
LIVE_GRID_PAUSED (optional)
     ↓
LIVE_GRID_RESUMED (optional)
     ↓
LIVE_GRID_STOPPED
     ↓
LIVE_GRID_SETTLED
     ↓
LIVE_GRID_REPORTED
```

All transitions are:

```text
- Logged
- Audited
- Notified to authorized users
```

---

# 10. Live Risk Limits

Live trading MUST have risk limits configured.

```text
RiskLimits
├── max_capital_per_grid
├── max_total_capital_deployed
├── max_capital_per_market
├── max_open_orders
├── max_drawdown_threshold
├── max_daily_loss_threshold
├── max_position_size
├── min_liquidity_requirement
├── max_spread_threshold
└── emergency_stop_conditions
```

## Risk Limit Enforcement

```text
Before every order:
  → Check risk limits
  → If violated → REJECT order
  → Log violation
  → Alert operator
```

---

# 11. Live Capital Management

```text
Capital Allocation:
├── Total available capital
├── Reserved capital (never deployed)
├── Deployable capital
├── Per-grid allocation
├── Per-section allocation
└── Reserve for recovery
```

## Capital Rules

```text
1. Never deploy more than approved amount
2. Always maintain reserve capital
3. Track capital usage in real-time
4. Alert on unusual capital consumption
5. Reconcile capital state periodically
```

---

# 12. Live Monitoring

## Required Monitoring

```text
Live Monitoring Dashboard:
├── OKX Live API connectivity
├── WebSocket status
├── Active live grids
├── Open orders count
├── Position sizes
├── Capital utilization
├── Realized P&L
├── Unrealized P&L
├── Drawdown status
├── Order flow rate
├── Error rate
├── Reconciliation status
└── Risk limit status
```

## Monitoring Frequency

```text
- Real-time: order flow, position, P&L
- Every minute: capital utilization, risk limits
- Every 5 minutes: reconciliation check
- Every hour: comprehensive health check
```

---

# 13. Live Alerting

## Alert Conditions

```text
CRITICAL (immediate action required):
- API connection lost
- WebSocket disconnected > 30s
- Reconciliation mismatch detected
- Risk limit breached
- Emergency stop triggered
- Unusual order rejection rate

WARNING (attention required):
- High error rate
- Capital utilization > 80%
- Drawdown approaching threshold
- Spread widening significantly
- Liquidity dropping

INFO (awareness):
- Grid state changes
- Order fills
- P&L milestones
- Reconciliation completed
```

## Alert Routing

```text
CRITICAL → LEVEL 3+ users (immediate)
WARNING → LEVEL 2+ users
INFO → LEVEL 2+ users (batched)
```

---

# 14. Live Order Execution

## Order Submission

```text
Grid Engine Decision
     ↓
Risk Limit Check
     ↓
Capital Check
     ↓
Execution Economics Check
     ↓
Order Construction
     ↓
OKX Adapter
     ↓
OKX Live API
     ↓
Order Acknowledged
     ↓
Track Order State
```

## Order State Tracking

```text
SUBMITTED
     ↓
ACKNOWLEDGED
     ↓
PARTIALLY_FILLED (possible)
     ↓
FILLED / CANCELLED / REJECTED
```

Every state transition is logged.

---

# 15. Live Reconciliation

## Purpose

Ensure internal state matches exchange state.

## Reconciliation Triggers

```text
1. Startup (mandatory)
2. WebSocket reconnection
3. Periodic (every 5 minutes)
4. After error recovery
5. Manual trigger
```

## Reconciliation Scope

```text
- Open orders
- Account balances
- Position sizes
- Recent fills
- Grid state consistency
```

## Reconciliation Mismatch

```text
If mismatch detected:
  1. Pause grid immediately
  2. Alert operator
  3. Log full state snapshot
  4. Investigate root cause
  5. Resolve mismatch
  6. Resume only after confirmation
```

---

# 16. Live Incident Response

## Incident Types

```text
1. Connection Loss
2. Order Submission Failure
3. Partial Fill Ambiguity
4. Reconciliation Mismatch
5. Risk Limit Breach
6. Exchange Downtime
7. Unusual Market Movement
8. System Error
```

## Response Procedures

### Connection Loss

```text
1. Detect connection loss
2. Pause all grid activity
3. Attempt reconnection with backoff
4. On reconnect: run reconciliation
5. Resume only after clean reconciliation
6. Log incident
```

### Order Submission Failure

```text
1. Log failure with full context
2. Check if order was actually submitted (timeout case)
3. Query OKX for order status
4. Reconcile state
5. Retry only if safe
6. Alert if repeated failures
```

### Reconciliation Mismatch

```text
1. Pause grid immediately
2. Snapshot all state
3. Compare internal vs exchange
4. Identify discrepancy
5. Resolve (may require manual intervention)
6. Confirm resolution
7. Resume with caution
8. Post-incident review
```

### Risk Limit Breach

```text
1. Stop order submission immediately
2. Alert operator
3. Evaluate current exposure
4. Determine if grid should stop
5. Take corrective action
6. Log breach details
```

### Exchange Downtime

```text
1. Detect exchange unavailability
2. Pause all grid activity
3. Monitor exchange status
4. Wait for recovery
5. Reconcile on recovery
6. Resume cautiously
```

---

# 17. Emergency Stop

## Trigger Conditions

```text
- Manual trigger by LEVEL 4+ user
- Risk limit critical breach
- Reconciliation mismatch unresolved
- System critical error
- Exchange anomaly detected
```

## Emergency Stop Procedure

```text
1. Stop all grid activity immediately
2. Cancel all open orders
3. Verify order cancellation
4. Snapshot current state
5. Calculate current exposure
6. Alert all authorized users
7. Log emergency stop event
8. Require manual review before resume
```

## Emergency Stop is NOT

```text
- Not a normal stop
- Not automatic recovery
- Not a pause
```

Emergency stop requires **explicit human review** before any resume.

---

# 18. Live Pause and Resume

## Pause

```text
- Stops new order submission
- Keeps existing orders active (or cancels, per config)
- Maintains state
- Can be resumed
```

## Resume

```text
- Requires authorization
- Runs pre-resume checks
- Reconciles state
- Resumes grid activity
```

## Pause vs Emergency Stop

| Aspect | Pause | Emergency Stop |
|---|---|---|
| Trigger | Normal operation | Critical condition |
| Recovery | Simple resume | Manual review required |
| State | Preserved | Snapshot + investigation |
| Authorization | LEVEL 3+ | LEVEL 4+ |

---

# 19. Live P&L Tracking

```text
Live P&L Tracking:
├── Realized P&L (completed round trips)
├── Unrealized P&L (open positions)
├── Total P&L
├── P&L by grid
├── P&L by market
├── P&L by section
├── Drawdown from peak
├── Capital utilization
└── Fee expenditure
```

P&L is:

```text
- Calculated deterministically
- Updated on every fill
- Reconciled periodically
- Never estimated by AI
```

---

# 20. Live Data Storage

Live trading data is stored separately and permanently.

```text
live_data/
├── orders/
├── fills/
├── grid_states/
├── account_snapshots/
├── pnl_records/
├── risk_events/
├── incidents/
├── approvals/
└── audit_logs/
```

Live data:

```text
- Is permanent (not purged)
- Is auditable
- May be used for post-trade analysis
- May inform future research (with caution)
- Is protected with access controls
```

---

# 21. Live Trading Policies

```text
1. Live trading requires LEVEL 3+ authorization
2. Live trading requires explicit approval
3. Live trading requires active monitoring
4. Live trading requires configured risk limits
5. Live trading requires clean reconciliation before start
6. Live trading can be stopped at any time by LEVEL 3+
7. Emergency stop can be triggered by LEVEL 4+
8. Live data is isolated from demo data
9. Live credentials are isolated from demo credentials
10. Live environment is clearly labeled in all interfaces
```

---

# 22. Live Trading Session

A live trading session is defined as:

```text
Session Start:
  - Approval valid
  - Grid started
  - Monitoring active

Session End:
  - Grid stopped
  - Orders settled
  - Reconciliation clean
  - Report generated
```

---

# 23. Live Trading Report

After each live trading session:

```text
Live Trading Report
├── Session: start → end
├── Blueprint: ID, market, sections
├── Capital: allocated, deployed, remaining
├── Orders: submitted, filled, cancelled, rejected
├── P&L: realized, unrealized, total
├── Drawdown: max, current
├── Fees: total paid
├── Risk events: count, details
├── Incidents: count, details
├── Reconciliation: clean / issues
├── Performance metrics
├── Observations
└── Recommendations
```

---

# 24. Live Trading Review

Periodic review of live trading performance:

```text
Weekly Review:
- P&L summary
- Risk events
- Incidents
- Strategy performance
- Market conditions

Monthly Review:
- Comprehensive performance analysis
- Model accuracy assessment
- Blueprint effectiveness
- Risk limit adequacy
- Operational improvements
```

---

# 25. Live Trading Restrictions

```text
Live trading is RESTRICTED when:

- Reconciliation is not clean
- Risk limits are not configured
- Monitoring is not active
- Approval has expired
- Emergency stop is active
- Exchange connectivity is unstable
- System health is degraded
- Capital is insufficient
```

---

# 26. Live Trading vs Research

```text
Research:
- Historical data
- Simulated outcomes
- No real funds
- Exploratory

Live Trading:
- Real-time data
- Real outcomes
- Real funds at risk
- Operational
```

Live trading results may inform future research, but:

```text
- Live data must be handled carefully
- Live outcomes are not guaranteed
- Past performance does not predict future
- Live trading is not an experiment
```

---

# 27. Live Trading Psychology

Operators must understand:

```text
1. Losses are possible and expected
2. Drawdowns will occur
3. Not every grid will be profitable
4. Market conditions change
5. Past success does not guarantee future success
6. Risk management is more important than profit
7. Emergency stop is a tool, not a failure
```

---

# 28. Non-Negotiable Rules

1. Live trading requires explicit approval from LEVEL 3+ user.
2. Live trading requires valid, unexpired approval.
3. Live trading requires configured risk limits.
4. Live trading requires active monitoring.
5. Live trading requires clean reconciliation before start.
6. Live trading uses separate credentials from demo.
7. Live trading data is stored separately and permanently.
8. Live trading can be stopped at any time.
9. Emergency stop requires manual review before resume.
10. Live P&L is calculated deterministically, never estimated.
11. Live environment is clearly labeled in all interfaces.
12. Live trading is restricted when system health is degraded.
13. Live trading approval is bound to specific blueprint and market.
14. Live trading approval has an expiry.
15. Live trading incidents are logged and reviewed.
16. Live trading reports are generated after each session.
17. Live trading is never automatic or unmonitored.
18. Live trading losses are possible and accepted.
19. Risk management takes priority over profit maximization.
20. Live trading is the highest-risk operational mode.

---

# 29. Final Definition

Live Trading is:

> **The highest-risk operational mode where real funds are deployed on exchange Spot markets (OKX, Binance, Bybit) through approved blueprints, enforced risk limits, active monitoring, and deterministic execution — requiring explicit approval, clean reconciliation, and emergency controls at all times.**

Live trading boundary:

```text
Research / Simulation
        ↓
Demo Validation
        ↓
Beta Multi-Tenant Validation
        ↓
Live Approval
        ↓
LIVE TRADING
        ↓
Monitoring + Risk Control
        ↓
Live Report
        ↓
Review + Learning
```

Live trading is where the system meets reality.

It must be treated with the highest level of discipline, caution, and respect.

The goal is not maximum profit.

The goal is **controlled, monitored, survivable trading** that can learn and improve over time.