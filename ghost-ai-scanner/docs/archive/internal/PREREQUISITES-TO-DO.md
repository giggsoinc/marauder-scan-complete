# PatronAI — Customer Prerequisites Checklist

**Prepared by:** Giggso Inc  
**Product:** PatronAI (formerly Marauder Scan / Ghost AI Scanner)  
**Version:** 1.1.0  
**Updated:** 2026-04-19  
**Classification:** CONFIDENTIAL

---

## How to use this document

Work through each section in order. Every item must be checked before running `setup.sh`. Items marked **[GIGGSO]** are completed by the Giggso team. Items marked **[CUSTOMER]** require action from your IT team.

Estimated total time: 2-4 hours for a first-time setup.

---

## Section 1 — AWS Account Access

> Your IT admin needs AWS CLI access with sufficient permissions before anything else can happen.

- [ ] **[CUSTOMER]** AWS account exists and is active
- [ ] **[CUSTOMER]** AWS CLI installed on the setup machine
  ```bash
  aws --version   # must return 2.x or higher
  ```
- [ ] **[CUSTOMER]** AWS CLI configured with credentials that have admin or power-user access
  ```bash
  aws configure
  # Enter: Access Key ID, Secret Access Key, Region, Output format
  aws sts get-caller-identity   # must return your account ID
  ```
- [ ] **[CUSTOMER]** Confirm target AWS region (recommend same region as your EC2 workloads)
  - Region: _______________
- [ ] **[CUSTOMER]** Confirm AWS account ID
  - Account ID: _______________

---

## Section 2 — EC2 Instance for Scanner

> PatronAI runs on a single EC2 instance for the demo. One EC2. All containers run here.

- [ ] **[CUSTOMER]** Launch EC2 instance
  - AMI: Amazon Linux 2023 or Ubuntu 24.04 LTS
  - Instance type: t3.medium minimum (2 vCPU, 4GB RAM)
  - Storage: 30GB root volume minimum
  - Key pair: create or select existing — you need SSH access
- [ ] **[CUSTOMER]** Note EC2 private IP address
  - Private IP: _______________
- [ ] **[CUSTOMER]** Note EC2 public IP address (if demo needs external access)
  - Public IP: _______________
- [ ] **[CUSTOMER]** EC2 security group configured — inbound rules:

  | Port | Protocol | Source | Purpose |
  |---|---|---|---|
  | 22 | TCP | Your office IP | SSH access |
  | 80 | TCP | Your office IP | Nginx reverse proxy |
  | 3000 | TCP | Your office IP | Grafana direct access |
  | 8501 | TCP | Your office IP | Streamlit settings |

  > **Important:** Never open ports 3000 or 8501 to 0.0.0.0/0. Office IP only.

- [ ] **[CUSTOMER]** SSH into EC2 and confirm connectivity
  ```bash
  ssh -i your-key.pem ec2-user@your-ec2-ip
  ```
- [ ] **[CUSTOMER]** Docker installed on EC2
  ```bash
  # Amazon Linux 2023
  sudo dnf install -y docker
  sudo systemctl start docker
  sudo systemctl enable docker
  sudo usermod -aG docker ec2-user

  # Ubuntu
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker ubuntu
  ```
- [ ] **[CUSTOMER]** Docker Compose installed on EC2
  ```bash
  sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
  docker-compose --version   # must return 2.x or higher
  ```
- [ ] **[CUSTOMER]** Git installed on EC2
  ```bash
  sudo dnf install -y git    # Amazon Linux
  sudo apt install -y git    # Ubuntu
  ```
- [ ] **[CUSTOMER]** PatronAI repo cloned onto EC2
  ```bash
  git clone https://github.com/giggso/patronai.git
  cd patronai
  ```
  > Existing deployments cloned from the `marauder-scan` repo remain valid — the
  > repo was renamed and auto-redirects.

---

## Section 3 — S3 Bucket

> `setup.sh` creates this automatically. But confirm the following before running it.

- [ ] **[CUSTOMER]** Decide on S3 bucket name
  - Format: `marauder-scan-{your-company-slug}` — example: `marauder-scan-acme`
    *(bucket prefix retained from v1 infra to preserve IAM policies and VPC Flow Log destinations)*
  - Must be globally unique across all AWS accounts
  - Lowercase, no spaces, no special characters except hyphens
  - Bucket name: _______________
- [ ] **[CUSTOMER]** Confirm S3 bucket does not already exist
  ```bash
  aws s3 ls s3://marauder-scan-your-company 2>&1
  # If "NoSuchBucket" appears — name is available. Good.
  # If bucket contents appear — name taken. Choose another.
  ```
- [ ] **[CUSTOMER]** Confirm S3 region matches EC2 region (avoids cross-region transfer costs)

---

## Section 4 — IAM Permissions

> `setup.sh` creates the scanner IAM user automatically. Your AWS account needs permission to do this.

- [ ] **[CUSTOMER]** Confirm your AWS credentials can create IAM users and policies
  ```bash
  aws iam get-user   # must not return AccessDenied
  ```
- [ ] **[CUSTOMER]** If your organisation restricts IAM user creation — ask your AWS admin to create:
  - IAM user: `patronai-scanner` (or the legacy `marauder-scan` name if re-using a v1 policy)
  - Attach the policy provided in `prodprep_readme.md` Section 2.1
  - Generate access key and share securely with Giggso team

---

## Section 5 — VPC Flow Logs

> VPC Flow Logs are the primary source of network traffic data. Must be enabled before scanner can detect anything.

- [ ] **[CUSTOMER]** Identify all VPCs where AI traffic monitoring is needed
  ```bash
  aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,Tags]' --output table
  ```
  - VPC IDs to monitor: _______________
- [ ] **[CUSTOMER]** Confirm VPC Flow Logs are not already enabled on target VPCs
  ```bash
  aws ec2 describe-flow-logs --filter "Name=resource-id,Values=vpc-xxxxxxxx"
  ```
- [ ] **[CUSTOMER]** If Flow Logs already enabled — confirm they ship to S3 (not CloudWatch only)
- [ ] **[GIGGSO]** `setup.sh` will enable VPC Flow Logs on confirmed VPCs automatically
- [ ] **[CUSTOMER]** Confirm there is no organisational policy blocking VPC Flow Log creation

---

## Section 6 — Network Firewall Logging (optional but recommended)

> Adds DNS-level visibility. Catches AI traffic even when VPC Flow Logs miss it.

- [ ] **[CUSTOMER]** Confirm whether AWS Network Firewall is deployed in your environment
  - Yes / No: _______________
- [ ] **[CUSTOMER]** If yes — confirm which firewall ARNs to enable logging on
  - Firewall ARNs: _______________
- [ ] **[GIGGSO]** Run `deploy/enable_firewall_logs.sh` with confirmed ARNs

---

## Section 7 — SNS Alerting

> Alerts fire to an SNS topic. Someone must receive them.

- [ ] **[CUSTOMER]** Confirm alert email address for SNS subscription
  - Alert email: _______________
- [ ] **[CUSTOMER]** Confirm Trinity webhook URL (if using TrinityOps)
  - Trinity webhook: _______________
- [ ] **[CUSTOMER]** After `setup.sh` runs — check email inbox and confirm SNS subscription
  - AWS sends a confirmation email. Click confirm. Without this no alerts arrive.

---

## Section 8 — Identity and Access Management for Scanner Dashboards

> Streamlit settings UI needs a list of who can log in and what role they have.

- [ ] **[CUSTOMER]** Provide list of email addresses allowed to access Streamlit settings UI

  | Email | Role |
  |---|---|
  | _______________ | Admin |
  | _______________ | Admin |
  | _______________ | Viewer |
  | _______________ | Viewer |

  Admin = can edit settings and trigger actions  
  Viewer = read-only health and stats

- [ ] **[CUSTOMER]** Confirm Grafana admin password (change from default before demo)
  - Password: _______________ (store securely — do not write here)

---

## Section 9 — Managed Devices (Laptops)

> Packetbeat and the thin agent run on managed laptops to capture endpoint-level AI traffic.

- [ ] **[CUSTOMER]** Confirm MDM platform in use
  - macOS: Jamf / Kandji / other: _______________
  - Windows: Intune / other: _______________
  - Linux: Ansible / Chef / other: _______________
- [ ] **[CUSTOMER]** Confirm IT admin has MDM package deployment rights
- [ ] **[CUSTOMER]** Confirm how many managed devices in scope
  - Device count: _______________
- [ ] **[CUSTOMER]** Identify pilot group for first agent rollout (recommend 10-20 devices)
  - Pilot group: _______________
- [ ] **[GIGGSO]** Will provide MDM-ready packages after `setup.sh` completes
- [ ] **[CUSTOMER]** Deploy pilot agent packages and confirm telemetry appearing in S3

---

## Section 10 — NAC and Identity Mapping (optional)

> Provides IP-to-user mapping when EC2 tags and Identity Center are not available.

- [ ] **[CUSTOMER]** Confirm whether NAC system is in use (Cisco ISE, Aruba, FortiNAC etc)
  - NAC system: _______________
- [ ] **[CUSTOMER]** If yes — export IP-to-MAC-to-username mapping CSV
  - Required columns: `ip, mac, username, department, location`
  - Upload to: `s3://marauder-scan-{company}/identity/nac-mapping.csv`
- [ ] **[CUSTOMER]** Confirm whether AWS Identity Center (SSO) is configured
  - Identity Center Store ID: _______________
- [ ] **[CUSTOMER]** Confirm whether Active Directory LDAP is accessible from the scanner EC2
  - LDAP URL: _______________
  - Base DN: _______________

---

## Section 11 — Network Access Control Log (from XLS templates)

> If using the provided XLS templates as a data source — upload these to S3 before first scan.

- [ ] **[CUSTOMER]** Export Network_Access_Control_Log.xlsx to CSV
- [ ] **[CUSTOMER]** Export Network_Traffic_Monitoring_Dashboard.xlsx data sheet to CSV
- [ ] **[CUSTOMER]** Export Security_Event_Correlation_Tracker.xlsx to CSV
- [ ] **[CUSTOMER]** Upload all three CSVs to `s3://marauder-scan-{company}/ocsf/manual/`
- [ ] **[GIGGSO]** Scanner normaliser will pick these up on first cycle automatically

---

## Section 11b — Regression Tests (run before first deploy)

> Validates the full PatronAI pipeline against LocalStack before touching real AWS. Runs in under 4 minutes. Generates an HTML report.

- [ ] **[SUPPORT TEAM]** Install test dependencies on the EC2 setup machine
  ```bash
  pip install pytest localstack-client --break-system-packages
  ```
- [ ] **[SUPPORT TEAM]** Pull LocalStack Docker image
  ```bash
  docker pull localstack/localstack:3.4
  ```
- [ ] **[SUPPORT TEAM]** Run full regression suite
  ```bash
  bash scripts/run_regression.sh
  ```
  Expected output:
  ```
  ✓ Unit tests:        45/45 passed
  ✓ Integration tests: 14/14 passed
  ✓ Docker build:      PASSED
  ✓ ALL TESTS PASSED — safe to merge
  ```
- [ ] **[SUPPORT TEAM]** Open HTML report and confirm all green
  ```bash
  # Report written to:
  ls reports/regression-*.html
  # Open in browser — dark theme, per-test pass/fail table
  ```
- [ ] **[SUPPORT TEAM]** If any test fails — do NOT proceed with deployment. Fix first.

> Re-run regression after every code change. Before every customer deployment.

---

## Section 12 — Pre-flight Verification

> Run these checks after `setup.sh` completes and before `docker-compose up`.

- [ ] `.env` file exists in repo root
  ```bash
  ls -la .env   # must exist, must not be empty
  ```
- [ ] S3 bucket exists and config files are seeded
  ```bash
  aws s3 ls s3://marauder-scan-{company}/config/
  # Must show: authorized.csv, unauthorized.csv, settings.json
  ```
- [ ] SNS subscription confirmed (check email inbox)
- [ ] Docker and docker-compose working
  ```bash
  docker ps
  docker-compose --version
  ```
- [ ] EC2 has outbound internet access (needed to pull Docker images)
  ```bash
  curl -I https://registry.hub.docker.com
  # Must return HTTP 200 or 301
  ```
- [ ] AWS credentials in .env are valid
  ```bash
  AWS_ACCESS_KEY_ID=$(grep AWS_ACCESS_KEY_ID .env | cut -d= -f2)
  AWS_SECRET_ACCESS_KEY=$(grep AWS_SECRET_ACCESS_KEY .env | cut -d= -f2)
  AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    aws s3 ls s3://marauder-scan-{company}/   # must list config/ prefix
  ```

---

## Section 13 — Go / No-Go Decision

Complete this table with the IT Admin and Giggso team before running docker-compose.

| Check | Status | Owner | Notes |
|---|---|---|---|
| EC2 running and accessible | | IT Admin | |
| S3 bucket created and seeded | | Giggso | |
| VPC Flow Logs enabled | | IT Admin | |
| SNS subscription confirmed | | IT Admin | |
| .env file generated | | Giggso | |
| Docker and compose installed | | IT Admin | |
| MDM pilot group identified | | IT Admin | |
| Allowed emails list provided | | IT Admin | |
| Security group rules confirmed | | IT Admin | |

**Sign-off:**

IT Admin: _______________ Date: _______________

Giggso team: _______________ Date: _______________

---

## Quick Reference — Run Order

Once all sections above are checked:

```bash
# Step 1: Run setup (if not already done)
bash scripts/setup.sh

# Step 2: Run regression tests — confirm all green before proceeding
bash scripts/run_regression.sh
# Open reports/regression-*.html in browser — must show ALL TESTS PASSED

# Step 3: Verify .env was generated
cat .env

# Step 4: Start all containers
docker-compose up -d

# Step 5: Check containers are running
docker-compose ps

# Step 6: Open Grafana
open http://your-ec2-ip:3000

# Step 7: Open Streamlit settings
open http://your-ec2-ip:8501

# Step 8: Check scanner logs
docker-compose logs -f scanner
```

---

## Support

Contact Giggso Inc for any prerequisites blockers before the scheduled deployment date.

*PatronAI by Giggso Inc · TrinityOps.ai · AIRTaaS*  
*This document is confidential and for authorised distribution only.*
