# Security Policy

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

If you discover a security issue in PatronAI, please report it privately by
emailing **security@giggso.com**.

Public disclosure of an unpatched vulnerability puts every PatronAI deployment
at risk. We ask that you give us reasonable time to triage and release a fix
before disclosing publicly. We will coordinate a disclosure date with you.

### PGP

If you need to encrypt the report, contact security@giggso.com first to request
a PGP public key.

---

## What to Include in a Report

Please provide as much of the following as possible to help us reproduce and
assess the issue quickly:

- **Description** — What is the vulnerability? What component is affected?
- **Impact** — What can an attacker do if they exploit this?
- **Steps to reproduce** — Minimal, reliable reproduction steps
- **Proof of concept** — Code snippet, screenshot, or packet capture (if safe to share)
- **Affected version(s)** — Output of `cat ghost-ai-scanner/VERSION`
- **Deployment type** — EC2 container, Docker Compose, or local Python
- **Environment** — OS, Python version, relevant config flags
- **Suggested fix** — Optional, but appreciated if you have one

---

## Response Timeline

| Stage | Target |
|-------|--------|
| Acknowledgement | Within 48 hours of receipt |
| Initial triage and severity assessment | Within 7 calendar days |
| Patch release for confirmed High/Critical issues | Within 30 calendar days |
| Coordinated public disclosure | Agreed with reporter |

We will keep you informed of progress throughout. If you have not received an
acknowledgement within 48 hours, follow up at security@giggso.com.

---

## Supported Versions

Security fixes are applied to the **latest release only**. We do not backport
patches to older versions.

| Version | Supported |
|---------|-----------|
| Latest release (see `ghost-ai-scanner/VERSION`) | Yes |
| All prior releases | No |

We recommend always running the latest tagged release.

---

## Security Design Notes

These properties are relevant to security researchers assessing the system:

### No credentials on edge devices

PatronAI scan agents are distributed as self-contained packages. They do not
store AWS credentials, database passwords, or API keys. Identity is established
at runtime through IAM roles (EC2 instance profile) or short-lived session tokens.

### OTP-locked installers

Agent packages are rendered with a one-time password embedded at build time.
A compromised agent package cannot be reused by a third party after that OTP
has been consumed.

### Presigned URLs only

Agent packages fetch their runtime configuration and upload findings exclusively
via S3 presigned URLs. No long-lived credentials are embedded in packages or
transmitted over the wire. Presigned URLs are scoped to specific S3 keys and
expire on a short TTL.

### All data stays in customer S3

PatronAI does not phone home. Scan findings, network logs, and user data are
written only to the customer's own S3 bucket (`patronai` by default). No data
is transmitted to Giggso infrastructure.

### Network traffic only — no kernel access

The scanner observes network connections via OS-level connection tables and
cloud flow logs. It does not require kernel modules, eBPF, or root access to the
monitored host.
