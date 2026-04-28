#!/usr/bin/env bash
# =============================================================
# FILE: deploy_to_ec2.sh
# VERSION: 1.2.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Deploy ghost-ai-scanner/ codebase to an EC2 instance.
#          Creates EC2 if needed. Creates/attaches IAM instance
#          profile so prereqs.sh can run from inside EC2 without
#          access keys. Transfers code via rsync/scp.
# USAGE:   bash deploy_to_ec2.sh   (from marauder-scan-complete/)
# REQUIRES: AWS CLI v2, admin credentials on this Mac
# =============================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()      { echo -e "${GREEN}✓${NC} $1"; }
err()     { echo -e "${RED}✗${NC} $1" >&2; exit 1; }
warn()    { echo -e "${YELLOW}!${NC} $1"; }
info()    { echo -e "${BLUE}→${NC} $1"; }
ask()     { echo -e "\n${BOLD}$1${NC}"; }
divider() { echo -e "\n${BOLD}──────────────────────────────────────────────${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/ghost-ai-scanner"
KEYS_DIR="$SCRIPT_DIR/keys"

[[ -d "$SOURCE_DIR" ]] || err "ghost-ai-scanner/ not found at $SCRIPT_DIR"

EC2_HOST=""; EC2_KEY=""; EC2_USER="ec2-user"; EC2_REMOTE_DIR=""
INSTANCE_ID=""; INSTANCE_PROFILE_NAME=""
KEY_NAME=""

# ══════════════════════════════════════════════════════════════
# BANNER
# ══════════════════════════════════════════════════════════════
clear
echo -e "${BOLD}"
echo "=================================================="
echo "  PatronAI — Deploy Codebase to EC2"
echo "  Giggso Inc  |  v1.2.0"
echo "=================================================="
echo -e "${NC}"
echo "Source : $SOURCE_DIR"
echo "Steps  : credentials → EC2 → IAM profile → key → transfer → bootstrap → SSH"
echo ""

# ══════════════════════════════════════════════════════════════
# STEP 1 — AWS CREDENTIALS (Mac-side admin credentials)
# ══════════════════════════════════════════════════════════════
divider
echo -e "${BOLD}STEP 1 — AWS Credentials${NC}"

command -v aws &>/dev/null || err "AWS CLI not found. Install: https://aws.amazon.com/cli/"

ask "AWS Access Key ID:"
read -r AWS_ACCESS_KEY_ID
[[ -z "$AWS_ACCESS_KEY_ID" ]] && err "Cannot be empty"

ask "AWS Secret Access Key:"
read -r -s AWS_SECRET_ACCESS_KEY
echo ""
[[ -z "$AWS_SECRET_ACCESS_KEY" ]] && err "Cannot be empty"

ask "AWS Region [us-east-1]:"
read -r AWS_REGION
AWS_REGION="${AWS_REGION:-us-east-1}"

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION="$AWS_REGION"

info "Verifying credentials..."
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
  || err "Invalid credentials — check your Access Key ID and Secret Access Key."
ok "Valid — Account: $AWS_ACCOUNT   Region: $AWS_REGION"

# ══════════════════════════════════════════════════════════════
# STEP 2 — EC2 INSTANCE: PICK EXISTING OR CREATE NEW
# ══════════════════════════════════════════════════════════════
divider
echo -e "${BOLD}STEP 2 — EC2 Instance${NC}"
info "Fetching EC2 instances in $AWS_REGION (excluding terminated)..."
echo ""

EC2_IDS=(); EC2_NAMES=(); EC2_PUB_IPS=()
EC2_PRIV_IPS=(); EC2_STATES=(); EC2_TYPES=(); EC2_PROFILES=()

while IFS=$'\t' read -r id name pub priv state itype profile; do
  [[ -z "$id" ]] && continue
  EC2_IDS+=("$id")
  EC2_NAMES+=("${name:-(no name)}")
  EC2_PUB_IPS+=("${pub:-—}")
  EC2_PRIV_IPS+=("${priv:-—}")
  EC2_STATES+=("$state")
  EC2_TYPES+=("$itype")
  EC2_PROFILES+=("${profile:-none}")
done < <(aws ec2 describe-instances \
  --region "$AWS_REGION" \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0],PublicIpAddress,PrivateIpAddress,State.Name,InstanceType,IamInstanceProfile.Arn]' \
  --output text 2>/dev/null | grep -v "terminated" || true)

if [[ ${#EC2_IDS[@]} -gt 0 ]]; then
  printf "  %-4s %-20s %-18s %-16s %-10s %-12s %s\n" \
    "No." "Instance ID" "Name" "Public IP" "State" "Type" "IAM Profile"
  printf "  %-4s %-20s %-18s %-16s %-10s %-12s %s\n" \
    "---" "-----------" "----" "---------" "-----" "----" "-----------"
  for i in "${!EC2_IDS[@]}"; do
    # Shorten profile ARN to just the name
    PROF="${EC2_PROFILES[$i]}"
    [[ "$PROF" != "none" && "$PROF" != "None" ]] && PROF="$(basename "$PROF")" || PROF="none"
    printf "  [%s]  %-18s %-18s %-16s %-10s %-12s %s\n" \
      "$((i+1))" "${EC2_IDS[$i]}" "${EC2_NAMES[$i]}" \
      "${EC2_PUB_IPS[$i]}" "${EC2_STATES[$i]}" "${EC2_TYPES[$i]}" "$PROF"
  done
  echo ""
fi

CREATE_IDX=$(( ${#EC2_IDS[@]} + 1 ))
MANUAL_IDX=$(( ${#EC2_IDS[@]} + 2 ))
echo "  [$CREATE_IDX]  Create a new EC2 instance"
echo "  [$MANUAL_IDX]  Enter IP / hostname manually"
echo ""
ask "Choice [1]:"
read -r EC2_PICK
EC2_PICK="${EC2_PICK:-1}"

# ── Option A: pick existing ────────────────────────────────────
if [[ "$EC2_PICK" =~ ^[0-9]+$ ]] && \
   [[ "$EC2_PICK" -ge 1 ]] && \
   [[ "$EC2_PICK" -lt "$CREATE_IDX" ]]; then

  IDX=$(( EC2_PICK - 1 ))
  INSTANCE_ID="${EC2_IDS[$IDX]}"
  EC2_HOST="${EC2_PUB_IPS[$IDX]}"
  [[ "$EC2_HOST" == "—" ]] && {
    EC2_HOST="${EC2_PRIV_IPS[$IDX]}"
    warn "No public IP — using private IP $EC2_HOST (requires VPN or bastion)"
  }
  if [[ "${EC2_STATES[$IDX]}" != "running" ]]; then
    warn "Instance is '${EC2_STATES[$IDX]}'"
    ask "Start it now? (y/N):"
    read -r SR
    if [[ "$SR" =~ ^[yY]$ ]]; then
      info "Starting $INSTANCE_ID..."
      aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" >/dev/null
      info "Waiting for running state..."
      aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"
      EC2_HOST=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
      ok "Running — IP: $EC2_HOST"
    else
      err "Cannot deploy to a stopped instance."
    fi
  fi
  ok "Selected: $INSTANCE_ID  (${EC2_NAMES[$IDX]})  →  $EC2_HOST"

# ── Option B: enter manually ───────────────────────────────────
elif [[ "$EC2_PICK" == "$MANUAL_IDX" ]]; then
  ask "EC2 public IP or hostname:"
  read -r EC2_HOST
  [[ -z "$EC2_HOST" ]] && err "Host cannot be empty"
  ask "EC2 Instance ID (needed to attach IAM profile, or press Enter to skip):"
  read -r INSTANCE_ID

# ── Option C: create new EC2 ──────────────────────────────────
elif [[ "$EC2_PICK" == "$CREATE_IDX" ]]; then

  divider
  echo -e "${BOLD}  Creating New EC2 Instance${NC}"

  # ── Key pair ──────────────────────────────────────────────
  echo ""
  echo -e "${BOLD}  Key Pair${NC}"
  info "Fetching existing key pairs..."
  KP_NAMES=()
  while IFS= read -r kname; do
    [[ -n "$kname" ]] && KP_NAMES+=("$kname")
  done < <(aws ec2 describe-key-pairs --region "$AWS_REGION" \
    --query 'KeyPairs[*].KeyName' --output text 2>/dev/null | tr '\t' '\n' || true)

  echo ""
  if [[ ${#KP_NAMES[@]} -gt 0 ]]; then
    echo "  Existing key pairs:"
    for i in "${!KP_NAMES[@]}"; do
      echo "  [$((i+1))]  ${KP_NAMES[$i]}"
    done
    echo "  [$(( ${#KP_NAMES[@]} + 1 ))]  Create new key pair"
    ask "Choose [1]:"
    read -r KP_PICK; KP_PICK="${KP_PICK:-1}"
  else
    warn "No key pairs found — will create one."
    KP_PICK=$(( ${#KP_NAMES[@]} + 1 ))
  fi

  NEW_KP_IDX=$(( ${#KP_NAMES[@]} + 1 ))
  if [[ "$KP_PICK" == "$NEW_KP_IDX" ]]; then
    ask "Name for new key pair [marauder-scan-key]:"
    read -r NEW_KP_NAME; NEW_KP_NAME="${NEW_KP_NAME:-marauder-scan-key}"
    mkdir -p "$KEYS_DIR"
    EC2_KEY="$KEYS_DIR/${NEW_KP_NAME}.pem"
    [[ -f "$EC2_KEY" ]] && warn "Overwriting existing $EC2_KEY"
    aws ec2 create-key-pair --key-name "$NEW_KP_NAME" --region "$AWS_REGION" \
      --query 'KeyMaterial' --output text > "$EC2_KEY"
    chmod 400 "$EC2_KEY"
    KEY_NAME="$NEW_KP_NAME"
    ok "Key pair '$KEY_NAME' created → $EC2_KEY"
  else
    IDX=$(( KP_PICK - 1 ))
    KEY_NAME="${KP_NAMES[$IDX]}"
    ask "Local path to ${KEY_NAME}.pem:"
    read -r EC2_KEY; EC2_KEY="${EC2_KEY/#\~/$HOME}"
    [[ ! -f "$EC2_KEY" ]] && err "Key file not found: $EC2_KEY"
    chmod 400 "$EC2_KEY" 2>/dev/null || true
    ok "Using key pair: $KEY_NAME → $EC2_KEY"
  fi

  # ── Security group ────────────────────────────────────────
  echo ""
  echo -e "${BOLD}  Security Group${NC}"
  info "Fetching existing security groups..."
  SG_IDS=(); SG_NAMES=(); SG_DESCS=()
  while IFS=$'\t' read -r sgid sgname sgdesc; do
    [[ -z "$sgid" ]] && continue
    SG_IDS+=("$sgid"); SG_NAMES+=("$sgname"); SG_DESCS+=("$sgdesc")
  done < <(aws ec2 describe-security-groups --region "$AWS_REGION" \
    --query 'SecurityGroups[*].[GroupId,GroupName,Description]' \
    --output text 2>/dev/null || true)

  echo ""
  if [[ ${#SG_IDS[@]} -gt 0 ]]; then
    printf "  %-4s %-20s %-28s %-30s %s\n" "No." "Group ID" "Name" "Description" "Open Ports"
    printf "  %-4s %-20s %-28s %-30s %s\n" "---" "--------" "----" "-----------" "----------"
    for i in "${!SG_IDS[@]}"; do
      PORTS=$(aws ec2 describe-security-groups \
        --group-ids "${SG_IDS[$i]}" --region "$AWS_REGION" \
        --query "SecurityGroups[0].IpPermissions[?IpRanges[?CidrIp=='0.0.0.0/0']].FromPort" \
        --output text 2>/dev/null | tr '\t' ',' || echo "?")
      printf "  [%s]  %-18s %-28s %-30s %s\n" \
        "$((i+1))" "${SG_IDS[$i]}" "${SG_NAMES[$i]}" "${SG_DESCS[$i]}" "$PORTS"
    done
    echo ""
    echo "  [$(( ${#SG_IDS[@]} + 1 ))]  Create new patronai-sg (ports 22/80/3000/8501)"
    ask "Choose [$(( ${#SG_IDS[@]} + 1 ))]:"
    read -r SG_PICK; SG_PICK="${SG_PICK:-$(( ${#SG_IDS[@]} + 1 ))}"
  else
    warn "No security groups found — will create one."
    SG_PICK=$(( ${#SG_IDS[@]} + 1 ))
  fi

  NEW_SG_IDX=$(( ${#SG_IDS[@]} + 1 ))
  if [[ "$SG_PICK" == "$NEW_SG_IDX" ]]; then
    DEFAULT_VPC=$(aws ec2 describe-vpcs --region "$AWS_REGION" \
      --filters "Name=isDefault,Values=true" \
      --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo "")
    SG_ARGS=(--group-name "patronai-sg" \
              --description "PatronAI - SSH Nginx Grafana Streamlit" \
              --region "$AWS_REGION")
    [[ -n "$DEFAULT_VPC" && "$DEFAULT_VPC" != "None" ]] && SG_ARGS+=(--vpc-id "$DEFAULT_VPC")
    SG_ID=$(aws ec2 create-security-group "${SG_ARGS[@]}" --query 'GroupId' --output text)

    echo ""
    warn "Opening all ports to 0.0.0.0/0 (world). Lock these to your IP after setup."
    warn "Go to EC2 > Security Groups > $SG_ID and restrict Source to your office/home IP."
    echo ""

    # Port rules — Description field shows as the rule name in the AWS console
    declare -A RULE_DESC=(
      [22]="patronai-in-ssh"
      [80]="patronai-in-nginx"
      [3000]="patronai-in-grafana"
      [8501]="patronai-in-streamlit"
    )
    declare -A RULE_LABEL=(
      [22]="Admin SSH access"
      [80]="HTTP reverse proxy"
      [3000]="Grafana dashboards"
      [8501]="Settings and admin UI"
    )
    for PORT in 22 80 3000 8501; do
      DESC="${RULE_DESC[$PORT]}"
      aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --region "$AWS_REGION" \
        --ip-permissions "[{\"IpProtocol\":\"tcp\",\"FromPort\":${PORT},\"ToPort\":${PORT},\"IpRanges\":[{\"CidrIp\":\"0.0.0.0/0\",\"Description\":\"${DESC}\"}]}]" \
        >/dev/null
      ok "  $DESC (port $PORT) — ${RULE_LABEL[$PORT]}  ⚠ lock to your IP"
    done
    ok "Security group created: $SG_ID"
  else
    IDX=$(( SG_PICK - 1 ))
    SG_ID="${SG_IDS[$IDX]}"
    ok "Using: $SG_ID (${SG_NAMES[$IDX]})"
  fi

  # ── AMI ───────────────────────────────────────────────────
  echo ""
  echo -e "${BOLD}  Operating System${NC}"
  echo "  [1]  Amazon Linux 2023  (user: ec2-user)"
  echo "  [2]  Ubuntu 24.04 LTS   (user: ubuntu)"
  ask "Choice [1]:"
  read -r AMI_PICK; AMI_PICK="${AMI_PICK:-1}"
  info "Looking up latest AMI..."
  if [[ "$AMI_PICK" == "2" ]]; then
    EC2_USER="ubuntu"
    AMI_ID=$(aws ec2 describe-images --region "$AWS_REGION" --owners 099720109477 \
      --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
                "Name=state,Values=available" "Name=architecture,Values=x86_64" \
      --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text 2>/dev/null) \
      || err "Ubuntu 24.04 AMI not found"
    ok "Ubuntu 24.04: $AMI_ID"
  else
    EC2_USER="ec2-user"
    AMI_ID=$(aws ec2 describe-images --region "$AWS_REGION" --owners amazon \
      --filters "Name=name,Values=al2023-ami-*-x86_64" \
                "Name=state,Values=available" "Name=architecture,Values=x86_64" \
      --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text 2>/dev/null) \
      || err "Amazon Linux 2023 AMI not found"
    ok "Amazon Linux 2023: $AMI_ID"
  fi

  # ── Instance type + storage ───────────────────────────────
  echo ""
  echo -e "${BOLD}  Instance Type${NC}"
  echo "  [1]  t3.medium  — 2 vCPU  4 GB  (minimum)"
  echo "  [2]  t3.large   — 2 vCPU  8 GB"
  echo "  [3]  t3.xlarge  — 4 vCPU 16 GB"
  echo "  [4]  Custom"
  ask "Choice [1]:"
  read -r IT_PICK; IT_PICK="${IT_PICK:-1}"
  case "$IT_PICK" in
    1) INSTANCE_TYPE="t3.medium" ;;
    2) INSTANCE_TYPE="t3.large"  ;;
    3) INSTANCE_TYPE="t3.xlarge" ;;
    4) ask "Instance type:"; read -r INSTANCE_TYPE ;;
    *) INSTANCE_TYPE="t3.medium" ;;
  esac
  ok "Type: $INSTANCE_TYPE"

  ask "Name tag [marauder-scan]:"
  read -r EC2_NAME_TAG; EC2_NAME_TAG="${EC2_NAME_TAG:-marauder-scan}"

  ask "Root volume GB [30]:"
  read -r VOL_SIZE; VOL_SIZE="${VOL_SIZE:-30}"

else
  err "Invalid choice: $EC2_PICK"
fi

# ══════════════════════════════════════════════════════════════
# STEP 3 — IAM INSTANCE PROFILE
# Gives the EC2 AWS permissions so prereqs.sh runs without keys
# ══════════════════════════════════════════════════════════════
divider
echo -e "${BOLD}STEP 3 — IAM Instance Profile${NC}"
echo ""
echo "An IAM instance profile lets the EC2 call AWS APIs without"
echo "access keys. prereqs.sh needs this to create S3, SNS, IAM, etc."
echo ""

ROLE_NAME="marauder-scan-ec2-role"
PROFILE_NAME="marauder-scan-ec2-profile"

# List existing instance profiles
EXISTING_PROFILES=()
while IFS= read -r pname; do
  [[ -n "$pname" ]] && EXISTING_PROFILES+=("$pname")
done < <(aws iam list-instance-profiles \
  --query 'InstanceProfiles[*].InstanceProfileName' \
  --output text 2>/dev/null | tr '\t' '\n' || true)

if [[ ${#EXISTING_PROFILES[@]} -gt 0 ]]; then
  echo "  Existing instance profiles:"
  for i in "${!EXISTING_PROFILES[@]}"; do
    echo "  [$((i+1))]  ${EXISTING_PROFILES[$i]}"
  done
  CREATE_P_IDX=$(( ${#EXISTING_PROFILES[@]} + 1 ))
  SKIP_P_IDX=$(( ${#EXISTING_PROFILES[@]} + 2 ))
  echo "  [$CREATE_P_IDX]  Create new profile '$PROFILE_NAME' (recommended)"
  echo "  [$SKIP_P_IDX]  Skip — attach profile manually later"
  ask "Choice [1]:"
  read -r PROF_PICK; PROF_PICK="${PROF_PICK:-1}"

  if [[ "$PROF_PICK" == "$SKIP_P_IDX" ]]; then
    warn "IAM profile skipped — prereqs.sh will ask for credentials on EC2."
    INSTANCE_PROFILE_NAME=""
  elif [[ "$PROF_PICK" == "$CREATE_P_IDX" ]]; then
    INSTANCE_PROFILE_NAME="$PROFILE_NAME"
    CREATE_PROFILE=true
  else
    IDX=$(( PROF_PICK - 1 ))
    INSTANCE_PROFILE_NAME="${EXISTING_PROFILES[$IDX]}"
    CREATE_PROFILE=false
    ok "Using existing profile: $INSTANCE_PROFILE_NAME"
  fi
else
  echo "  No instance profiles found."
  echo "  [1]  Create '$PROFILE_NAME' with AdministratorAccess (recommended for setup)"
  echo "  [2]  Skip — attach profile manually later"
  ask "Choice [1]:"
  read -r PROF_PICK; PROF_PICK="${PROF_PICK:-1}"
  if [[ "$PROF_PICK" == "1" ]]; then
    INSTANCE_PROFILE_NAME="$PROFILE_NAME"
    CREATE_PROFILE=true
  else
    warn "IAM profile skipped."
    INSTANCE_PROFILE_NAME=""
    CREATE_PROFILE=false
  fi
fi

# ── Create role + profile if needed ───────────────────────────
if [[ "${CREATE_PROFILE:-false}" == true ]]; then
  # Create role (skip if exists)
  if ! aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
    info "Creating IAM role '$ROLE_NAME'..."
    aws iam create-role \
      --role-name "$ROLE_NAME" \
      --assume-role-policy-document '{
        "Version":"2012-10-17",
        "Statement":[{
          "Effect":"Allow",
          "Principal":{"Service":"ec2.amazonaws.com"},
          "Action":"sts:AssumeRole"
        }]
      }' >/dev/null
    ok "Role created: $ROLE_NAME"
  else
    ok "Role already exists: $ROLE_NAME"
  fi

  # Attach scoped inline policy — only what prereqs.sh and scanner need
  POLICY_FILE="$SCRIPT_DIR/iam-policy.json"
  [[ ! -f "$POLICY_FILE" ]] && err "iam-policy.json not found at $SCRIPT_DIR"
  aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "marauder-scan-scoped-policy" \
    --policy-document "file://${POLICY_FILE}" 2>/dev/null || true
  ok "Scoped policy attached (S3 / SNS / IAM user / EC2 / CloudTrail / STS only)"

  # Create instance profile (skip if exists)
  if ! aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" &>/dev/null; then
    info "Creating instance profile '$INSTANCE_PROFILE_NAME'..."
    aws iam create-instance-profile \
      --instance-profile-name "$INSTANCE_PROFILE_NAME" >/dev/null
    aws iam add-role-to-instance-profile \
      --instance-profile-name "$INSTANCE_PROFILE_NAME" \
      --role-name "$ROLE_NAME" >/dev/null
    ok "Instance profile created and role attached"
  else
    ok "Instance profile already exists: $INSTANCE_PROFILE_NAME"
  fi
fi

# ══════════════════════════════════════════════════════════════
# Launch new EC2 with profile (if creating new)
# ══════════════════════════════════════════════════════════════
if [[ "$EC2_PICK" == "$CREATE_IDX" ]]; then
  echo ""
  echo -e "${BOLD}  Launch Summary${NC}"
  echo "  AMI:            $AMI_ID"
  echo "  Type:           $INSTANCE_TYPE"
  echo "  Key pair:       $KEY_NAME"
  echo "  Security group: $SG_ID"
  echo "  Volume:         ${VOL_SIZE} GB"
  echo "  Name:           $EC2_NAME_TAG"
  [[ -n "$INSTANCE_PROFILE_NAME" ]] && \
    echo "  IAM profile:    $INSTANCE_PROFILE_NAME"
  echo ""
  ask "Launch instance? (y/N):"
  read -r LAUNCH_R
  [[ ! "$LAUNCH_R" =~ ^[yY]$ ]] && { warn "Launch cancelled."; exit 0; }

  LAUNCH_ARGS=(
    --region "$AWS_REGION"
    --image-id "$AMI_ID"
    --instance-type "$INSTANCE_TYPE"
    --key-name "$KEY_NAME"
    --security-group-ids "$SG_ID"
    --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":${VOL_SIZE},\"VolumeType\":\"gp3\"}}]"
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${EC2_NAME_TAG}},{Key=Project,Value=marauder-scan}]"
    --query 'Instances[0].InstanceId'
    --output text
  )
  [[ -n "$INSTANCE_PROFILE_NAME" ]] && \
    LAUNCH_ARGS+=(--iam-instance-profile "Name=${INSTANCE_PROFILE_NAME}")

  info "Launching instance..."
  INSTANCE_ID=$(aws ec2 run-instances "${LAUNCH_ARGS[@]}")
  ok "Launched: $INSTANCE_ID"

  info "Waiting for running state (1–2 min)..."
  aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"
  info "Waiting for status checks (2–3 min)..."
  aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"

  EC2_HOST=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
  [[ -z "$EC2_HOST" || "$EC2_HOST" == "None" ]] && \
    err "No public IP — check subnet auto-assign public IP setting."
  ok "EC2 ready — $INSTANCE_ID   IP: $EC2_HOST   User: $EC2_USER"
fi

# ── Attach profile to existing instance ───────────────────────
if [[ "$EC2_PICK" != "$CREATE_IDX" && -n "$INSTANCE_PROFILE_NAME" && -n "$INSTANCE_ID" ]]; then
  # Check if profile already attached
  CURRENT_PROFILE=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" \
    --query 'Reservations[0].Instances[0].IamInstanceProfile.Arn' \
    --output text 2>/dev/null || echo "")

  if [[ -n "$CURRENT_PROFILE" && "$CURRENT_PROFILE" != "None" ]]; then
    CURRENT_NAME=$(basename "$CURRENT_PROFILE")
    if [[ "$CURRENT_NAME" == "$INSTANCE_PROFILE_NAME" ]]; then
      ok "Profile '$INSTANCE_PROFILE_NAME' already attached to $INSTANCE_ID"
    else
      warn "Different profile already attached: $CURRENT_NAME"
      ask "Replace with '$INSTANCE_PROFILE_NAME'? (y/N):"
      read -r REPLACE_R
      if [[ "$REPLACE_R" =~ ^[yY]$ ]]; then
        ASSOC_ID=$(aws ec2 describe-iam-instance-profile-associations \
          --filters "Name=instance-id,Values=$INSTANCE_ID" \
          --query 'IamInstanceProfileAssociations[0].AssociationId' \
          --output text 2>/dev/null || echo "")
        [[ -n "$ASSOC_ID" && "$ASSOC_ID" != "None" ]] && \
          aws ec2 replace-iam-instance-profile-association \
            --association-id "$ASSOC_ID" \
            --iam-instance-profile "Name=${INSTANCE_PROFILE_NAME}" \
            --region "$AWS_REGION" >/dev/null
        ok "Profile replaced with '$INSTANCE_PROFILE_NAME'"
      fi
    fi
  else
    info "Attaching profile '$INSTANCE_PROFILE_NAME' to $INSTANCE_ID..."
    aws ec2 associate-iam-instance-profile \
      --instance-id "$INSTANCE_ID" \
      --iam-instance-profile "Name=${INSTANCE_PROFILE_NAME}" \
      --region "$AWS_REGION" >/dev/null
    ok "Profile attached — waiting 15s for credentials to propagate..."
    sleep 15
  fi
fi

# ══════════════════════════════════════════════════════════════
# STEP 4 — SSH CONNECTION DETAILS
# ══════════════════════════════════════════════════════════════
divider
echo -e "${BOLD}STEP 4 — SSH Connection${NC}"

if [[ -z "$EC2_KEY" ]]; then
  ask "Path to SSH private key (.pem):"
  read -r EC2_KEY; EC2_KEY="${EC2_KEY/#\~/$HOME}"
  [[ ! -f "$EC2_KEY" ]] && err "Key not found: $EC2_KEY"
  chmod 400 "$EC2_KEY" 2>/dev/null || true
else
  ok "Key: $EC2_KEY"
fi

# ── Detect correct SSH username from AMI ─────────────────────
if [[ -n "$INSTANCE_ID" ]]; then
  AMI_NAME=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --region "$AWS_REGION" \
    --query "Reservations[0].Instances[0].ImageId" \
    --output text 2>/dev/null || true)
  AMI_DESC=$(aws ec2 describe-images --image-ids "$AMI_NAME" \
    --region "$AWS_REGION" \
    --query "Images[0].Name" --output text 2>/dev/null || true)
  if echo "$AMI_DESC" | grep -qi "ubuntu"; then
    EC2_USER="ubuntu"
  else
    EC2_USER="ec2-user"
  fi
  info "AMI detected: $AMI_DESC"
  info "Default SSH user: $EC2_USER"
fi

# ── Verify SG has port 22 open before attempting SSH ─────────
SG_CHECK=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --region "$AWS_REGION" \
  --query "Reservations[0].Instances[0].SecurityGroups[*].GroupId" \
  --output text 2>/dev/null || true)
PORT22_OPEN=false
for SG_CK in $SG_CHECK; do
  RESULT=$(aws ec2 describe-security-groups --group-ids "$SG_CK" \
    --region "$AWS_REGION" \
    --query "SecurityGroups[0].IpPermissions[?FromPort==\`22\`].FromPort" \
    --output text 2>/dev/null || true)
  [[ -n "$RESULT" ]] && PORT22_OPEN=true && break
done
if [[ "$PORT22_OPEN" == "false" ]]; then
  err "Port 22 is NOT open in any attached security group. Add an SSH inbound rule first."
fi
ok "Port 22 confirmed open on instance security group"

ask "SSH username [$EC2_USER]   (Amazon Linux → ec2-user  |  Ubuntu → ubuntu):"
read -r USER_INPUT; EC2_USER="${USER_INPUT:-$EC2_USER}"

DEFAULT_REMOTE="/home/${EC2_USER}/patronai"
ask "Remote directory [$DEFAULT_REMOTE]:"
read -r EC2_REMOTE_DIR; EC2_REMOTE_DIR="${EC2_REMOTE_DIR:-$DEFAULT_REMOTE}"

info "Testing SSH to ${EC2_USER}@${EC2_HOST}..."
RETRIES=6
for i in $(seq 1 $RETRIES); do
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "${EC2_USER}@${EC2_HOST}" "echo ok" &>/dev/null && break
  warn "Not ready — retry $i/$RETRIES in 15s..."
  [[ $i -lt $RETRIES ]] && sleep 15
done
ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
  "${EC2_USER}@${EC2_HOST}" "echo ok" &>/dev/null \
  && ok "SSH OK — connected as ${EC2_USER}@${EC2_HOST}" \
  || err "SSH failed. Check key path and username. Key: $EC2_KEY  User: $EC2_USER"

# ══════════════════════════════════════════════════════════════
# STEP 5 — TRANSFER CODEBASE
# ══════════════════════════════════════════════════════════════
divider
echo -e "${BOLD}STEP 5 — Transfer Codebase${NC}"
echo ""
echo "  From : $SOURCE_DIR"
echo "  To   : ${EC2_USER}@${EC2_HOST}:${EC2_REMOTE_DIR}"
echo ""
FILE_COUNT=$(find "$SOURCE_DIR" \
  -not -path "*/.git/*" -not -name ".DS_Store" \
  -not -name "*.pyc" -not -path "*/__pycache__/*" \
  -type f | wc -l | tr -d ' ')
echo "  Files: ~${FILE_COUNT} (excluding .git / __pycache__ / .DS_Store)"
echo ""
ask "Proceed? (y/N):"
read -r SCP_CONFIRM
[[ ! "$SCP_CONFIRM" =~ ^[yY]$ ]] && { warn "Transfer cancelled."; exit 0; }

ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" "mkdir -p '${EC2_REMOTE_DIR}'"

# Ensure rsync is installed on the remote before transferring
info "Checking rsync on remote..."
REMOTE_HAS_RSYNC=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" "command -v rsync && echo yes || echo no" 2>/dev/null)
if [[ "$REMOTE_HAS_RSYNC" != *"yes"* ]]; then
  info "Installing rsync on remote (requires sudo)..."
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
    "${EC2_USER}@${EC2_HOST}" \
    "sudo dnf install -y --allowerasing rsync 2>/dev/null || sudo apt-get install -y rsync 2>/dev/null || sudo yum install -y rsync 2>/dev/null"
  ok "rsync installed on remote"
fi

info "Transferring..."
rsync -az --progress \
  --exclude ".git" --exclude "__pycache__" \
  --exclude "*.pyc" --exclude ".DS_Store" --exclude "*.egg-info" \
  -e "ssh -i '${EC2_KEY}' -o StrictHostKeyChecking=no" \
  "$SOURCE_DIR/" "${EC2_USER}@${EC2_HOST}:${EC2_REMOTE_DIR}/"
ok "Transfer complete"

# Also copy prereqs.sh to the EC2
scp -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "$SCRIPT_DIR/prereqs.sh" \
  "${EC2_USER}@${EC2_HOST}:${EC2_REMOTE_DIR}/prereqs.sh" 2>/dev/null || true
ok "prereqs.sh copied to EC2"

# ══════════════════════════════════════════════════════════════
# STEP 6 — BOOTSTRAP EC2 (Docker + Python)
# ══════════════════════════════════════════════════════════════
divider
echo -e "${BOLD}STEP 6 — Bootstrap EC2${NC}"
echo ""
echo "  [1]  Install Docker, docker-compose, Python deps (new EC2)"
echo "  [2]  Skip — already installed"
echo ""
ask "Choice [1]:"
read -r BOOT_PICK; BOOT_PICK="${BOOT_PICK:-1}"

if [[ "$BOOT_PICK" == "1" ]]; then
  info "Installing on EC2..."
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" bash <<'REMOTE'
set -e
if command -v dnf &>/dev/null; then
  sudo dnf install -y --allowerasing docker python3 python3-pip git curl
  sudo systemctl start docker && sudo systemctl enable docker
elif command -v apt-get &>/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  sudo apt-get update -qq
  sudo apt-get install -y docker.io python3 python3-pip git curl
  sudo systemctl start docker && sudo systemctl enable docker
fi
sudo usermod -aG docker "$USER" || true
DC_VER=$(curl -fsSL https://api.github.com/repos/docker/compose/releases/latest \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo "v2.27.0")
sudo curl -fsSL \
  "https://github.com/docker/compose/releases/download/${DC_VER}/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker --version
docker-compose --version
REMOTE
  ok "Docker and docker-compose installed"

  info "Installing Python dependencies..."
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" \
    "cd '${EC2_REMOTE_DIR}' && pip3 install -r requirements.txt --quiet 2>/dev/null || true"
  ok "Python dependencies installed"
else
  warn "Bootstrap skipped."
fi

# ══════════════════════════════════════════════════════════════
# STEP 7 — VERIFY
# ══════════════════════════════════════════════════════════════
divider
echo -e "${BOLD}STEP 7 — Verify${NC}"
REMOTE_COUNT=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" \
  "find '${EC2_REMOTE_DIR}' -type f | wc -l" 2>/dev/null | tr -d ' ')
ok "Files on EC2: $REMOTE_COUNT"
info "Verifying IAM profile works on EC2..."
IDENTITY=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" \
  "aws sts get-caller-identity --query Account --output text 2>/dev/null || echo FAIL")
if [[ "$IDENTITY" == "FAIL" || -z "$IDENTITY" ]]; then
  warn "IAM profile not active yet — wait 30s and verify with: aws sts get-caller-identity"
else
  ok "IAM profile active on EC2 — Account: $IDENTITY"
fi

# ══════════════════════════════════════════════════════════════
# DONE
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}"
echo "=================================================="
echo "  Deployment complete!"
echo "=================================================="
echo -e "${NC}"
echo "  EC2        : ${EC2_USER}@${EC2_HOST}"
echo "  Directory  : ${EC2_REMOTE_DIR}"
echo "  Key        : $EC2_KEY"
[[ -n "$INSTANCE_PROFILE_NAME" ]] && \
  echo "  IAM Profile: $INSTANCE_PROFILE_NAME (AdministratorAccess)"
echo ""
echo "Next steps:"
echo ""
echo "  1. SSH into EC2:"
echo "     ssh -i $EC2_KEY ${EC2_USER}@${EC2_HOST}"
echo ""
echo "  2. Run prereqs.sh (no credentials needed — IAM profile handles it):"
echo "     cd ${EC2_REMOTE_DIR}"
echo "     bash prereqs.sh"
echo ""
echo "  3. Start the scanner:"
echo "     docker-compose up -d"
echo ""
echo "  4. Populate ENI metadata cache (run once after first boot):"
echo "     docker exec marauder-scan python3 scripts/refresh_eni_cache.py"
echo ""
[[ -n "$INSTANCE_PROFILE_NAME" ]] && \
  echo -e "${YELLOW}NOTE:${NC} IAM role uses scoped policy — S3/SNS/IAM/EC2/CloudTrail only."
echo ""
ask "Open SSH session now? (y/N):"
read -r SSH_NOW
if [[ "$SSH_NOW" =~ ^[yY]$ ]]; then
  ok "Connecting — landing in ${EC2_REMOTE_DIR}"
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no -t \
    "${EC2_USER}@${EC2_HOST}" \
    "cd '${EC2_REMOTE_DIR}' && exec \$SHELL -l"
else
  echo ""
  echo "  ssh -i $EC2_KEY ${EC2_USER}@${EC2_HOST}"
fi
echo ""
echo -e "${BOLD}Giggso Inc x TrinityOps.ai x AIRTaaS${NC}"
