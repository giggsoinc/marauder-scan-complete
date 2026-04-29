# GitHub Repository Metadata Recommendations

This file captures the recommended settings for the PatronAI GitHub repository.
Apply these when the repo goes public.

---

## Repository Description

```
Open-source AI endpoint monitor — detect shadow AI, ghost AI, and unmanaged LLM
usage across your organisation. Streamlit dashboard · Hook agents · MCP server.
```

## Topics / Tags

```
ai-security  shadow-ai  llm-governance  endpoint-monitoring  streamlit
python  docker  mcp-server  compliance  zero-trust  ai-risk
```

## Website

```
https://patronai.giggso.com
```

*(or the GitHub Pages URL if the site hasn't launched yet)*

---

## Social Preview Image

Use `assets/branding/patronai-logo.png` or commission a 1280×640 OG card showing:
- Dark navy background (#0A0F1F)
- PatronAI wordmark + shield icon
- Tagline: "See every AI tool your team is using"

---

## Branch Protection (main)

| Setting | Value |
|---------|-------|
| Require PR before merging | ✅ |
| Required approvals | 1 |
| Dismiss stale approvals on push | ✅ |
| Require status checks | `unit-tests (3.12)`, `lint` |
| Require branches to be up to date | ✅ |
| Restrict force pushes | ✅ |
| Restrict deletions | ✅ |

---

## Security Settings

| Setting | Value |
|---------|-------|
| Private vulnerability reporting | ✅ Enabled |
| Dependabot alerts | ✅ Enabled |
| Dependabot security updates | ✅ Enabled |
| Secret scanning | ✅ Enabled |
| Push protection | ✅ Enabled |

---

## Labels to Create

| Name | Color | Description |
|------|-------|-------------|
| `bug` | `#d73a4a` | Something is broken |
| `enhancement` | `#a2eeef` | New feature or improvement |
| `provider-detection` | `#0075ca` | New AI provider coverage request |
| `rules` | `#e4e669` | Detection rule changes |
| `documentation` | `#0075ca` | Docs improvements |
| `good first issue` | `#7057ff` | Good for newcomers |
| `help wanted` | `#008672` | Extra attention needed |
| `triage` | `#e99695` | Needs initial review |
| `security` | `#b60205` | Security-related issue |
| `wontfix` | `#ffffff` | This will not be worked on |

---

## Milestones

| Milestone | Goal |
|-----------|------|
| `v1.1.0` | SMTP email alerts module |
| `v1.2.0` | Multi-tenant S3 isolation |
| `v2.0.0` | Cloud-managed SaaS mode |

---

## CODEOWNERS

Create `.github/CODEOWNERS`:

```
# Global owner — review required for all files
* @giggso

# Detection rules need extra care
ghost-ai-scanner/config/providers_deny.csv @giggso
ghost-ai-scanner/config/providers_allow.csv @giggso
ghost-ai-scanner/config/rules/ @giggso
```
