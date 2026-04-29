# GitHub Repository — Manual Settings Checklist

Complete these steps in the GitHub web UI **before making the repository public**.

---

## 1. Rename repository

**Action required in GitHub Settings → General → Repository name:**

```
Rename to: patronai
```

Full canonical URL after rename:
```
https://github.com/giggsoinc/patronai
```

Until the rename is done, all clone URLs in docs that reference
`https://github.com/giggsoinc/patronai.git` will 404. GitHub
automatically redirects the old name after rename.

---

## 2. Repository description

Set in **Settings → General → Description:**

```
Apache 2.0 AI endpoint monitoring for shadow AI, ghost AI assets, and unmanaged LLM usage.
```

---

## 3. Repository website

```
https://patronai.giggso.com
```

*(or the GitHub Pages URL if the site hasn't launched yet)*

---

## 4. Topics / Tags

Add in **Settings → General → Topics:**

```
ai-security  shadow-ai  ghost-ai  llm-security  ai-governance
endpoint-security  api-security  appsec  secops  cloud-security
ocsf  mcp  secret-scanning  aws-security  localstack  docker
python  monitoring  observability  compliance  self-hosted
open-source  apache-2-0
```

---

## 5. Social preview image

Upload in **Settings → General → Social preview:**

Use `assets/branding/patronai-logo.png` or a 1280×640 OG card with:
- Dark navy background (#0A0F1F)
- PatronAI wordmark + shield icon
- Tagline: "See every AI tool your team is using"

---

## 6. CODEOWNERS

Update `.github/CODEOWNERS` — replace `@REPLACE_WITH_MAINTAINER_HANDLE`
with the actual GitHub handle(s) of the maintainer(s).

---

## 7. Branch protection — main

Configure in **Settings → Branches → Add branch protection rule** for `main`:

| Setting | Value |
|---------|-------|
| Require pull request before merging | ✅ |
| Required approvals | 1 |
| Dismiss stale approvals on push | ✅ |
| Require status checks | `unit-tests (3.12)`, `lint` |
| Require branches to be up to date | ✅ |
| Restrict force pushes | ✅ |
| Restrict deletions | ✅ |

---

## 8. Security settings

Configure in **Settings → Security:**

| Setting | Value |
|---------|-------|
| Private vulnerability reporting | ✅ Enable |
| Dependabot alerts | ✅ Enable |
| Dependabot security updates | ✅ Enable |
| Secret scanning | ✅ Enable |
| Push protection | ✅ Enable |

---

## 9. GitHub Labels

Create in **Issues → Labels → New label:**

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

## 10. Milestones

Create in **Issues → Milestones:**

| Milestone | Goal |
|-----------|------|
| `v1.1.0` | SMTP email alerts module |
| `v1.2.0` | Multi-tenant S3 isolation |
| `v2.0.0` | Cloud-managed SaaS mode |

---

## 11. Release tag

Create release `v1.1.0` in **Releases → Draft a new release** only when
the version number in `ghost-ai-scanner/main.py` (or equivalent) is
confirmed accurate. Do not create the release tag before confirming.

---

## 12. Discussions

Enable in **Settings → Features → Discussions**.

After enabling, update `.github/PULL_REQUEST_TEMPLATE.md` and
`CONTRIBUTING.md` to use the live Discussions URL:
`https://github.com/giggsoinc/patronai/discussions`

---

## Summary checklist

- [ ] Repository renamed to `patronai`
- [ ] Description set
- [ ] Topics added
- [ ] Social preview uploaded
- [ ] CODEOWNERS maintainer handles filled in
- [ ] Branch protection on `main` configured
- [ ] Security / secret scanning enabled
- [ ] Labels created
- [ ] Discussions enabled
- [ ] Release tag created (only when version confirmed)
