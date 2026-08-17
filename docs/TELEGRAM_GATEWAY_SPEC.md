# TELEGRAM GATEWAY SPECIFICATION

---

# 1. Purpose

The Telegram Gateway is the user-facing messaging interface that allows authorized operators to interact with the AI Trading Grid system through Telegram commands and notifications.

It is a **thin translation layer** between Telegram and the Application Control API.

---

# 2. Core Principle

```text
Telegram Gateway
     ↓
Application Control API
     ↓
Business Services
```

The Telegram Gateway:

- Translates Telegram messages into API calls
- Translates API responses into Telegram messages
- Does NOT contain business logic
- Does NOT contain strategy logic
- Does NOT access exchange credentials
- Does NOT access AI provider credentials
- Does NOT bypass authentication or authorization

---

# 3. Architectural Position

```text
USER (Telegram App)
       ↓
Telegram Bot API (Cloud)
       ↓
Telegram Gateway Service
       ↓
Application Control API
       ↓
Use Cases / Engines
       ↓
Exchange / AI / Research
```

The Telegram Gateway is an **external client** of the Application Control API, equivalent in privilege to a Web UI or CLI.

---

# 4. Communication Mode

## Webhook Mode (Preferred)

```text
Telegram Cloud
     ↓ HTTPS POST
Telegram Gateway /webhook endpoint
     ↓
Process Update
     ↓
Call Application API
     ↓
Send Response via Telegram Bot API
```

Advantages:

- Lower latency
- No polling overhead
- Scales with Telegram's delivery

## Polling Mode (Fallback)

```text
Telegram Gateway
     ↓ getUpdates (long polling)
Telegram Bot API
     ↓
Process Update
```

Polling mode may be used during development or when webhook infrastructure is unavailable.

Production should use Webhook mode.

---

# 5. Gateway Responsibilities

The Telegram Gateway is responsible for:

```text
1. Receiving Telegram updates
2. Validating update authenticity
3. Extracting user identity
4. Mapping Telegram user to application identity
5. Parsing commands and arguments
6. Calling Application Control API
7. Formatting API responses for Telegram
8. Sending notifications and alerts
9. Handling Telegram-specific errors
10. Rate limiting per user
```

The Telegram Gateway is NOT responsible for:

```text
1. Business logic
2. Strategy decisions
3. Order execution
4. Risk validation
5. Market data processing
6. ML inference
7. Credential management
8. Data persistence (beyond session state)
```

---

# 6. Telegram User Identity

Every Telegram update contains:

```text
update
├── message
│   ├── from
│   │   ├── id (Telegram user ID)
│   │   ├── username
│   │   └── first_name
│   ├── chat
│   │   ├── id
│   │   └── type (private / group / supergroup)
│   ├── text
│   └── entities
└── callback_query
```

The Gateway must extract:

```text
telegram_user_id
telegram_username
chat_id
message_text
```

---

# 7. User Mapping

Telegram user IDs must be mapped to application identities.

```text
TelegramUserID
     ↓
UserMapping Table
     ↓
ApplicationUserID
     ↓
Role / Permission Level
```

Example mapping:

```text
telegram_user_id: 123456789
application_user_id: "operator-001"
role: "OPERATOR"
authorization_level: 3
```

Unmapped Telegram users must be rejected.

---

# 7.1 Open Access Mode (Beta Trial)

For beta testing, the Gateway supports an **open access mode** that allows any Telegram user to interact with the bot without pre-registration.

```text
TELEGRAM_OPEN_ACCESS=true
```

When enabled:

```text
1. Any Telegram user can send /start and use the bot
2. Users are auto-provisioned with a temporary identity on first interaction
3. Admin approval workflows still require TELEGRAM_ADMIN_USER_ID
4. Config allowlist (TELEGRAM_ALLOWED_USER_IDS) is bypassed
5. Database-linked identity check is bypassed
```

**Security constraints:**

```text
1. Open access is intended for BETA TRIAL only, NOT production
2. MUST be set to false in production environments
3. Dangerous operations (live trading, emergency stop) still require approval
4. All actions are still audit logged with Telegram user ID
5. Rate limiting still applies per user
```

**Configuration:**

```bash
# .env.local (beta trial)
TELEGRAM_OPEN_ACCESS=true

# .env (production)
TELEGRAM_OPEN_ACCESS=false
```

---

# 8. Authorization Levels

The Gateway enforces Telegram-level access control before calling the API.

```text
LEVEL 0 — Read-only
LEVEL 1 — Research / Simulation
LEVEL 2 — Demo Grid Control
LEVEL 3 — Live Grid Control
LEVEL 4 — Emergency Control
```

The Gateway checks:

```text
1. Is the Telegram user mapped?
2. Is the user authorized for this command?
3. Is the command allowed in the current environment?
4. Does the command require explicit approval?
```

If any check fails, the Gateway returns an authorization error message.

---

# 9. Command Registry

## Research Commands

```text
/research
→ GET /api/v1/research/recommendations

/market <SYMBOL>
→ GET /api/v1/research/market/{market_id}

/universe
→ GET /api/v1/research/universe
```

## Blueprint Commands

```text
/blueprint <SYMBOL>
→ GET /api/v1/blueprints/{market_id}/latest

/blueprint list
→ GET /api/v1/blueprints
```

## Simulation Commands

```text
/simulate <SYMBOL>
→ POST /api/v1/simulations

/simstatus <SIM_ID>
→ GET /api/v1/simulations/{simulation_id}
```

## Grid Control Commands

```text
/grid start <BLUEPRINT_ID>
→ POST /api/v1/grid/start

/grid pause <GRID_ID>
→ POST /api/v1/grid/{grid_id}/pause

/grid resume <GRID_ID>
→ POST /api/v1/grid/{grid_id}/resume

/grid stop <GRID_ID>
→ POST /api/v1/grid/{grid_id}/stop

/grid status
→ GET /api/v1/grid
```

## System Commands

```text
/status
→ GET /api/v1/system/status

/readiness
→ GET /api/v1/system/readiness

/help
→ Local help text (no API call)
```

## Emergency Commands

```text
/emergency-stop
→ POST /api/v1/grid/emergency-stop
```

Emergency commands require LEVEL 4 authorization.

---

# 10. Command Parsing

The Gateway parses commands from message text.

```text
Input: "/market BTC"

Parsed:
  command: "market"
  arguments: ["BTC"]
```

Parsing rules:

```text
1. Command starts with "/"
2. Command name is case-insensitive
3. Arguments are space-separated
4. Extra whitespace is trimmed
5. Unknown commands return help text
6. Missing arguments return usage text
```

---

# 11. Argument Validation

Before calling the API, the Gateway validates arguments.

```text
/market BTC
→ market_id = "BTC-USDT" (normalized)

/grid start BP-0042
→ blueprint_id = "BP-0042" (format validated)
```

Validation is **syntactic only**. Business validation happens in the API.

---

# 12. Response Formatting

API responses must be formatted for Telegram's message constraints.

## Text Formatting

```text
Telegram supports:
- Plain text
- Markdown (limited subset)
- HTML (limited subset)
```

Recommended: Use HTML formatting for structured responses.

## Message Length Limit

```text
Telegram max message length: 4096 characters
```

If response exceeds limit:

```text
1. Split into multiple messages
2. Summarize with "full details via /status"
3. Use inline keyboard for navigation
```

## Example Response

```text
📊 Market Recommendation

Market: BTC/USDT
Rank: #1
Recommendation: HIGH_PRIORITY
Suitability: 0.91
Confidence: 0.88
Regime: CORRECTIVE_BULLISH
Execution Quality: HIGH
```

---

# 13. Inline Keyboards

For interactive responses, use inline keyboards.

```text
{
  "inline_keyboard": [
    [
      {"text": "View Blueprint", "callback_data": "blueprint:BTC-USDT"},
      {"text": "Simulate", "callback_data": "simulate:BTC-USDT"}
    ],
    [
      {"text": "Start Grid", "callback_data": "start:BP-0042"}
    ]
  ]
}
```

Callback queries must be answered to remove loading state.

---

# 14. Notification Flow

The Gateway receives application events and pushes notifications.

```text
Application Event
     ↓
Event Bus / Webhook
     ↓
Telegram Gateway
     ↓
Format Notification
     ↓
Send to Authorized Users
```

## Notification Types

```text
GridStarted
GridPaused
GridResumed
GridStopped
OrderFilled
OrderRejected
RiskStateChanged
ReconciliationRequired
RecommendationUpdated
SimulationCompleted
```

## Notification Routing

```text
Event Type → Target Users
GridStarted → LEVEL 2+ users
OrderFilled → LEVEL 2+ users
RiskStateChanged → LEVEL 3+ users
EmergencyStop → LEVEL 4 users
```

---

# 15. Notification Format

```text
🔔 Grid Event

Type: OrderFilled
Grid: GRID-001
Market: BTC/USDT
Side: BUY
Price: 42,150.00
Quantity: 0.001
Time: 2026-08-15 17:30:00 UTC
```

---

# 16. Error Handling

## Telegram API Errors

```text
- Rate limit exceeded → Backoff and retry
- Chat not found → Remove user from notification list
- Bot blocked by user → Mark user as unreachable
- Message too long → Split or truncate
```

## Application API Errors

```text
- 401 Unauthorized → "Authentication required"
- 403 Forbidden → "Insufficient permissions"
- 404 Not Found → "Resource not found"
- 409 Conflict → "Operation conflict"
- 422 Validation → "Invalid request: {details}"
- 500 Internal → "System error, try again later"
```

Error messages must not leak internal details.

---

# 17. Rate Limiting

The Gateway applies per-user rate limiting.

```text
Read commands: 30/minute
Research commands: 10/minute
Control commands: 5/minute
Emergency commands: 2/minute
```

Exceeded limits return:

```text
⚠️ Rate limit exceeded. Please wait {seconds}s.
```

---

# 18. Session State

The Gateway may maintain minimal session state.

```text
SessionState
├── telegram_user_id
├── last_command
├── pending_approval
└── conversation_context
```

Session state must be:

```text
- Short-lived (timeout after inactivity)
- Non-sensitive (no credentials, no tokens)
- Recoverable (stateless restart possible)
```

---

# 19. Approval Flow

Dangerous operations require explicit approval.

```text
User: /grid start BP-0042
Gateway: 
  ⚠️ Confirm Live Grid Start
  
  Blueprint: BP-0042
  Market: BTC/USDT
  Environment: LIVE
  
  [Confirm] [Cancel]
```

User clicks [Confirm]:

```text
Gateway:
  → POST /api/v1/grid/start
  → Include approval confirmation
  → Include user identity
```

Approval is bound to:

```text
- Specific operation
- Specific blueprint
- Specific environment
- Specific user
- Time window
```

---

# 20. Environment Awareness

The Gateway must know the current environment.

```text
DEMO → Demo trading commands allowed
LIVE → Live trading commands require LEVEL 3+
```

The Gateway displays environment in responses:

```text
📊 Grid Status [DEMO]
```

or:

```text
📊 Grid Status [LIVE] ⚠️
```

---

# 21. Security Requirements

## Bot Token Protection

```text
- Bot token stored in secure secret storage
- Never logged
- Never exposed in responses
- Rotated on suspicion of compromise
```

## Webhook Security

```text
- HTTPS only
- Validate Telegram certificate
- Use secret_token header validation
- Reject requests from unknown sources
```

## User Whitelist

```text
- Only mapped Telegram users can interact
- Unmapped users receive "Unauthorized" response
- Mapping changes require admin approval
```

## Input Sanitization

```text
- All user input sanitized before processing
- No command injection
- No format string injection
- Length limits enforced
```

---

# 22. Logging

The Gateway logs:

```text
- Telegram user ID (not username for privacy)
- Command executed
- Timestamp
- API response status
- Error codes
```

The Gateway never logs:

```text
- Bot token
- API credentials
- Full message content (if sensitive)
- User personal data beyond ID
```

---

# 23. Health Check

The Gateway exposes:

```text
GET /health
→ { "status": "healthy", "telegram_connected": true }
```

Health depends on:

```text
- Telegram Bot API reachable
- Application Control API reachable
- Webhook registered (if webhook mode)
```

---

# 24. Deployment

```text
Telegram Gateway
├── Webhook Receiver (HTTPS)
├── Command Parser
├── User Mapper
├── API Client
├── Response Formatter
├── Notification Sender
└── Rate Limiter
```

The Gateway should be:

```text
- Stateless (or minimal state)
- Horizontally scalable
- Restartable without data loss
- Monitorable via health checks
```

---

# 25. Testing

Required tests:

```text
- Command parsing
- User mapping
- Authorization enforcement
- API integration
- Response formatting
- Error handling
- Rate limiting
- Notification delivery
- Webhook validation
- Approval flow
```

---

# 26. Non-Negotiable Rules

1. Telegram Gateway is a thin translation layer.
2. Telegram Gateway does not contain business logic.
3. Telegram Gateway does not access exchange credentials.
4. Telegram Gateway does not access AI provider credentials.
5. All commands go through Application Control API.
6. User identity must be mapped and authorized.
7. Unmapped users are rejected.
8. Dangerous operations require explicit approval.
9. Environment (DEMO/LIVE) must be visible in responses.
10. Bot token must never be logged or exposed.
11. Rate limiting is enforced per user.
12. Error messages must not leak internal details.
13. Notifications are routed by authorization level.
14. The Gateway must be restartable without state loss.
15. Webhook mode is preferred for production.

---

# 27. Final Definition

The Telegram Gateway is:

> **The user-facing messaging interface that translates Telegram commands and notifications into Application Control API calls, enforcing user mapping, authorization, rate limiting, and approval flows while remaining a stateless, business-logic-free translation layer.**

Final boundary:

```text
USER (Telegram)
     ↓
Telegram Bot API
     ↓
Telegram Gateway
     ↓
Application Control API
     ↓
Business Services
     ↓
Exchange / AI / Research
```

The Gateway provides convenience and accessibility.

It does not provide intelligence, strategy, or execution.

Those remain in their respective layers.