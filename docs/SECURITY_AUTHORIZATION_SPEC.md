# SECURITY & AUTHORIZATION SPECIFICATION

---

# 1. Purpose

This document defines the security architecture, credential management, authentication, authorization, and protection policies for the AI Trading Grid system.

Security is a **cross-cutting concern** that applies to every layer:

```text
Telegram Gateway
Application Control API
AI Research
Realtime AI
Grid Engine
Execution Engine
OKX Adapter
Data Storage
```

---

# 2. Core Security Principles

```text
1. Least Privilege
2. Defense in Depth
3. Zero Trust for External Inputs
4. Secrets Never Leave Secure Boundaries
5. Every Action is Auditable
6. Fail Secure (deny by default)
7. Environment Isolation (DEMO vs LIVE)
```

---

# 3. Threat Model Overview

## Assets to Protect

```text
- OKX API credentials (key, secret, passphrase)
- AI provider credentials (LLM API keys)
- Telegram bot token
- User personal data
- Trading strategy parameters
- Historical research data
- Model artifacts
- Application configuration
```

## Threat Actors

```text
- External attacker (network)
- Malicious insider
- Compromised dependency
- Telegram user impersonation
- Man-in-the-middle
- Credential leakage via logs
```

## Attack Surfaces

```text
- Telegram webhook endpoint
- Application Control API
- OKX REST/WebSocket connections
- AI provider API calls
- Database / storage
- Logging pipeline
- Configuration files
- Deployment pipeline
```

---

# 4. Credential Inventory

| Credential | Owner | Usage | Storage |
|---|---|---|---|
| OKX API Key | OKX Adapter | REST auth | Secret Manager |
| OKX API Secret | OKX Adapter | Signature | Secret Manager |
| OKX Passphrase | OKX Adapter | Signature | Secret Manager |
| Telegram Bot Token | Telegram Gateway | Bot API | Secret Manager |
| AI Provider API Key | AI Service | LLM calls | Secret Manager |
| Database Credentials | Application | Data access | Secret Manager |
| JWT Signing Key | Application | Token signing | Secret Manager |

---

# 5. Secret Storage

## Requirements

```text
- Secrets stored in dedicated secret manager
- Encrypted at rest
- Access controlled by identity
- Versioned for rotation
- Audit logged on access
```

## Prohibited Storage

```text
- Plain text files in repository
- Environment variables in code
- Hardcoded in source
- Logged in application logs
- Stored in Telegram messages
- Stored in ML datasets
- Included in API responses
```

## Recommended Secret Managers

```text
- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- GCP Secret Manager
- OS-level encrypted keystore (for local dev)
```

---

# 6. OKX API Key Security

## Key Permissions

```text
REQUIRED:
- Read (account info, market data)
- Trade (order placement)

DISABLED:
- Withdraw (must be disabled at OKX)
```

## Key Restrictions

```text
- Bind to IP whitelist (server IPs)
- Separate keys for DEMO and LIVE
- Never share keys between environments
- Rotate on personnel change or suspicion
```

## Key Lifecycle

```text
1. Create at OKX with minimal permissions
2. Store in Secret Manager
3. Application reads at startup
4. Key never appears in logs
5. Rotate periodically (90 days recommended)
6. Revoke immediately on compromise
```

---

# 7. Telegram Bot Token Security

```text
- Token stored in Secret Manager
- Only Telegram Gateway service can access
- Token never logged
- Token never sent in messages
- Webhook uses secret_token validation
- Rotate token if bot is compromised
```

## 7.1 Telegram Open Access Mode (Beta Trial Exception)

For beta testing, the system supports an open access mode:

```text
TELEGRAM_OPEN_ACCESS=true
```

**Security constraints:**

```text
1. Open access is for BETA TRIAL only — NEVER enable in production
2. All actions are still audit logged with Telegram user ID
3. Dangerous operations (live trading, emergency stop) still require approval
4. Rate limiting still applies per user
5. Credential storage remains encrypted per-user
6. Admin workflows (TELEGRAM_ADMIN_USER_ID) remain enforced
```

**Production requirement:**

```text
TELEGRAM_OPEN_ACCESS=false  # MANDATORY in production
```

See TELEGRAM_GATEWAY_SPEC.md Section 7.1 for full details.

---

# 8. AI Provider Credential Security

```text
- API keys stored in Secret Manager
- Only AI service layer can access
- Keys never included in prompts
- Keys never included in datasets
- Keys never logged
- Usage monitored for anomaly
```

---

# 9. Authentication

## API Authentication

The Application Control API requires authentication for all non-public endpoints.

```text
Client Request
     ↓
Authentication Middleware
     ↓
Identity Extracted
     ↓
Authorization Check
     ↓
Use Case Execution
```

## Supported Methods

```text
1. API Key (for service-to-service)
2. JWT Bearer Token (for user sessions)
3. mTLS (for high-security internal calls)
```

## API Key Authentication

```text
Header: X-API-Key: <key>
```

- Key mapped to service identity
- Key hashed and compared (never plain compare)
- Rate limited per key
- Revocable

## JWT Authentication

```text
Header: Authorization: Bearer <token>
```

JWT claims:

```text
{
  "sub": "operator-001",
  "role": "OPERATOR",
  "level": 3,
  "iat": 1723712345,
  "exp": 1723715945
}
```

- Short expiry (1 hour recommended)
- Signed with strong key
- Validated on every request
- Revocable via token blacklist

---

# 10. Authorization Model

## Role-Based Access Control (RBAC)

```text
Role → Permission Level → Allowed Operations
```

## Defined Roles

| Role | Level | Permissions |
|---|---|---|
| VIEWER | 0 | Read-only queries |
| RESEARCHER | 1 | Research, simulation |
| DEMO_OPERATOR | 2 | Demo grid control |
| LIVE_OPERATOR | 3 | Live grid control |
| EMERGENCY_ADMIN | 4 | Emergency stop, system control |
| SYSTEM_ADMIN | 5 | User management, configuration |

## Permission Matrix

| Operation | VIEWER | RESEARCHER | DEMO_OP | LIVE_OP | EMERGENCY | ADMIN |
|---|---|---|---|---|---|---|
| Read status | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Research | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Simulate | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Demo grid | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Live grid | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Emergency stop | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| User management | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

# 11. Authorization Enforcement

Authorization is enforced at multiple layers:

```text
1. Telegram Gateway (user mapping + level check)
2. Application Control API (role + permission check)
3. Use Case layer (operation-specific check)
4. Environment guard (DEMO/LIVE policy)
```

Deny by default:

```text
If no explicit permission → DENY
```

---

# 12. Environment Guards

## Environment Definitions

```text
DEMO — OKX Demo Trading, no real funds
LIVE — OKX Live Trading, real funds at risk
```

## Environment-Specific Policies

| Policy | DEMO | LIVE |
|---|---|---|
| Grid start | LEVEL 2+ | LEVEL 3+ + approval |
| Grid stop | LEVEL 2+ | LEVEL 3+ |
| Emergency stop | LEVEL 4 | LEVEL 4 |
| Research | LEVEL 1+ | LEVEL 1+ |
| Simulation | LEVEL 1+ | LEVEL 1+ |

## Environment Isolation

```text
- DEMO and LIVE use separate OKX API keys
- DEMO and LIVE may use separate database schemas
- Configuration explicitly declares environment
- Code paths do not mix environments
- A LIVE operation can never accidentally hit DEMO endpoint
```

---

# 13. Approval Workflow

Dangerous operations require explicit approval.

```text
Request
  ↓
Authorization Check
  ↓
Approval Required?
  ├── No → Execute
  └── Yes → Create Approval Request
              ↓
         Notify Approver
              ↓
         Approver Confirms
              ↓
         Execute with Approval Record
```

## Approval-Bound Operations

```text
- Live grid start
- Live grid resume after emergency stop
- Blueprint modification in LIVE
- User role elevation
- API key rotation
```

## Approval Record

```text
ApprovalRecord
├── approval_id
├── operation_id
├── requested_by
├── approved_by
├── timestamp
├── environment
├── operation_details
└── expiry
```

---

# 14. Audit Logging

Every security-relevant event must be logged.

```text
AuditLog
├── audit_id
├── timestamp
├── actor_id
├── actor_type (user / service / system)
├── action
├── resource
├── environment
├── result (success / denied / error)
├── correlation_id
└── metadata
```

## Audited Events

```text
- Authentication success/failure
- Authorization denial
- Command execution
- Approval grant/deny
- Grid start/stop/pause/resume
- Order submission
- Configuration change
- Secret access
- User mapping change
```

## Audit Log Protection

```text
- Append-only (no modification)
- Stored separately from application data
- Retained for minimum 1 year
- Access restricted to SYSTEM_ADMIN
- Alert on unauthorized access attempt
```

---

# 15. Network Security

## TLS Everywhere

```text
- All external communication over TLS 1.2+
- Internal service communication over TLS or trusted network
- Certificate validation enabled
- No self-signed certs in production
```

## API Endpoint Protection

```text
- HTTPS only
- Rate limiting
- Request size limits
- CORS restricted
- WAF for public endpoints
```

## OKX Connection Security

```text
- REST over HTTPS
- WebSocket over WSS
- Certificate pinning (optional, with fallback)
- IP whitelist on OKX side
```

---

# 16. Input Validation

All external input must be validated.

```text
- Telegram messages: length, format, encoding
- API requests: schema validation
- Query parameters: type, range, format
- File uploads: type, size (if applicable)
```

## Validation Layers

```text
1. Transport layer (size limits)
2. API layer (schema validation)
3. Use case layer (business validation)
4. Domain layer (invariant validation)
```

---

# 17. Injection Prevention

```text
- No SQL injection: parameterized queries only
- No command injection: no shell execution from user input
- No format string injection: controlled formatting
- No XSS: output encoding for web UI
- No path traversal: validated file paths
```

---

# 18. Rate Limiting

## API Rate Limits

```text
- Read endpoints: 100 req/min per identity
- Research endpoints: 20 req/min per identity
- Control endpoints: 10 req/min per identity
- Live operations: 5 req/min per identity
```

## Brute Force Protection

```text
- Authentication failures: lockout after 5 attempts
- Lockout duration: 15 minutes
- Alert on repeated failures
```

---

# 19. Logging Security

## What to Log

```text
- Request ID / correlation ID
- Actor identity (hashed if sensitive)
- Action performed
- Resource accessed
- Result status
- Timestamp
```

## What NEVER to Log

```text
- OKX API secret
- OKX passphrase
- Telegram bot token
- AI provider API keys
- JWT signing keys
- Full authentication headers
- Personal user data (beyond ID)
- Full request bodies (if sensitive)
```

## Log Protection

```text
- Logs stored in access-controlled location
- Log retention policy defined
- Logs not accessible from Telegram/API responses
- Alert on unusual log access patterns
```

---

# 20. Dependency Security

```text
- Dependencies pinned to specific versions
- Vulnerability scanning in CI/CD
- No dependencies with known critical CVEs
- License compliance checked
- Minimal dependency footprint
```

---

# 21. Deployment Security

```text
- Secrets injected at runtime (not build time)
- Container images scanned
- Minimal base images
- No credentials in image layers
- Deployment access restricted
- Rollback capability maintained
```

---

# 22. Incident Response

## Security Incident Types

```text
- Credential compromise
- Unauthorized access detected
- Data breach
- Denial of service
- Anomalous trading behavior
- Telegram bot hijack
```

## Response Procedure

```text
1. Detect (monitoring / alert)
2. Contain (revoke credentials, isolate service)
3. Assess (scope, impact)
4. Remediate (rotate keys, patch, fix)
5. Recover (restore service)
6. Review (post-incident analysis)
```

## Emergency Controls

```text
- Emergency stop all grids
- Revoke OKX API keys at exchange
- Disable Telegram bot
- Freeze live trading
```

---

# 23. OKX-Specific Security

## API Key Creation Checklist

```text
☑ Read permission enabled
☑ Trade permission enabled
☑ Withdraw permission DISABLED
☑ IP whitelist configured
☑ Separate keys for DEMO and LIVE
☑ Keys stored in Secret Manager
☑ Passphrase stored separately from key
```

## OKX Account Security

```text
- 2FA enabled on OKX account
- Strong, unique password
- Login notifications enabled
- API activity monitored
```

---

# 24. Data Protection

## Data Classification

| Data | Sensitivity | Protection |
|---|---|---|
| OKX credentials | CRITICAL | Secret Manager, encrypted |
| User personal data | HIGH | Access controlled, minimal |
| Trading strategy | HIGH | Access controlled |
| ML models | MEDIUM | Versioned, access controlled |
| Market data | LOW | Standard storage |
| Public research | LOW | Standard storage |

## Encryption

```text
- At rest: AES-256 or equivalent
- In transit: TLS 1.2+
- Secrets: dedicated encryption in Secret Manager
```

---

# 25. Security Testing

Required security tests:

```text
- Authentication bypass attempts
- Authorization escalation attempts
- Injection attacks
- Rate limit enforcement
- Secret leakage scan (logs, responses)
- Dependency vulnerability scan
- Penetration testing (periodic)
```

---

# 26. Security Review Checklist

Before any release:

```text
☑ No secrets in code or config files
☑ All endpoints require authentication (except public)
☑ Authorization enforced on all operations
☑ Audit logging active
☑ Rate limiting configured
☑ Input validation on all external input
☑ TLS enabled on all connections
☑ Dependency scan passed
☑ Secret rotation procedure documented
☑ Incident response procedure documented
```

---

# 27. Non-Negotiable Rules

1. Secrets are stored in a dedicated secret manager.
2. Secrets never appear in logs, responses, or datasets.
3. OKX API keys have Read + Trade only; Withdraw is disabled.
4. Separate credentials for DEMO and LIVE environments.
5. All API endpoints require authentication except explicitly public.
6. Authorization is deny-by-default.
7. Dangerous operations require explicit approval.
8. Every security-relevant action is audit logged.
9. Audit logs are append-only and access-controlled.
10. All external communication uses TLS.
11. Input validation is applied at every boundary.
12. Rate limiting protects against abuse and brute force.
13. Dependencies are scanned for vulnerabilities.
14. Incident response procedure is documented and tested.
15. Security review is mandatory before release.
16. Telegram bot token is protected like exchange credentials.
17. AI provider credentials are isolated from strategy layers.
18. User mapping changes require admin approval.
19. Environment isolation between DEMO and LIVE is absolute.
20. Fail secure: errors result in denial, not permission.

---

# 28. Final Definition

The Security & Authorization layer is:

> **The cross-cutting protection system that secures credentials, authenticates identities, enforces role-based authorization, mandates approval for dangerous operations, maintains immutable audit trails, and isolates DEMO and LIVE environments across every layer of the AI Trading Grid system.**

Security boundary:

```text
EXTERNAL INPUT
     ↓
Authentication
     ↓
Authorization
     ↓
Approval (if required)
     ↓
Audit Log
     ↓
Use Case Execution
     ↓
Protected Resources
```

Security is not a feature.

It is the foundation that makes every other feature trustworthy.