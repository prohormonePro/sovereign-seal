# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

If you discover a security vulnerability in `sovereign-seal`, please report it responsibly.

**Email:** prohormonepro@gmail.com

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

**Response time:** We aim to acknowledge reports within 48 hours and provide a fix within 7 days for critical issues.

## Scope

`sovereign-seal` is a governance primitive, not a complete security solution. It provides:

- **Tamper detection** via SHA-256 hash chains
- **Consensus verification** via witness tip comparison
- **Output governance** via configurable voice checks

It does **not** provide:

- Encryption at rest or in transit
- Access control or authentication
- Network security
- Key management

These are the responsibility of the deploying infrastructure.

## Design Philosophy

The system's security model is simple: **halt on any anomaly**. There is no "warn and continue" mode. If integrity cannot be proven, the system stops. This is by design.
