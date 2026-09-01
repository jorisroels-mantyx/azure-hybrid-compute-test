#!/usr/bin/env bash
# Deploys Azure infrastructure and configures it for Arc-based job submission.
#
# Covers:
#   1. Deploy resource group, ACR, and Log Analytics via Bicep
#   2. Create a service principal for Arc node onboarding and write credentials to .env
#
# Required env vars (source .env before running):
#   AZURE_SUBSCRIPTION_ID, AZURE_LOCATION, AZURE_RESOURCE_GROUP, AZURE_ACR_NAME

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$(cd "$SCRIPT_DIR/.." && pwd)/.env"

: "${AZURE_SUBSCRIPTION_ID:?}"
: "${AZURE_LOCATION:?}"
: "${AZURE_RESOURCE_GROUP:?}"
: "${AZURE_ACR_NAME:?}"

# ── Step 1: Deploy Azure infrastructure ──────────────────────────────────────

echo "==> Deploying Azure infrastructure..."
az deployment sub create \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location "$AZURE_LOCATION" \
  --template-file "$SCRIPT_DIR/main.bicep" \
  --parameters "$SCRIPT_DIR/main.bicepparam" \
  --parameters location="$AZURE_LOCATION" resourceGroupName="$AZURE_RESOURCE_GROUP" acrName="$AZURE_ACR_NAME" \
  --output none

echo "==> Infrastructure deployed."

# ── Step 2: Create service principal for Arc node onboarding ─────────────────

echo "==> Creating service principal for Arc onboarding..."
SP_JSON=$(az ad sp create-for-rbac \
  --name "arc-onboarding-sp" \
  --role "Azure Connected Machine Onboarding" \
  --scopes "/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$AZURE_RESOURCE_GROUP" \
  --output json)

TENANT_ID=$(echo "$SP_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tenant'])")
SP_ID=$(echo "$SP_JSON"     | python3 -c "import sys,json; print(json.load(sys.stdin)['appId'])")
SP_SECRET=$(echo "$SP_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")

# Write / update credentials in .env
for KEY_VAL in \
  "AZURE_TENANT_ID=$TENANT_ID" \
  "AZURE_SERVICE_PRINCIPAL_ID=$SP_ID" \
  "AZURE_SERVICE_PRINCIPAL_SECRET=$SP_SECRET"
do
  KEY="${KEY_VAL%%=*}"
  VAL="${KEY_VAL#*=}"
  if grep -q "^${KEY}=" "$ENV_FILE" 2>/dev/null; then
    sed -i.bak "s|^${KEY}=.*|${KEY}=${VAL}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
  else
    echo "${KEY}=${VAL}" >> "$ENV_FILE"
  fi
done

export AZURE_TENANT_ID="$TENANT_ID"
export AZURE_SERVICE_PRINCIPAL_ID="$SP_ID"
export AZURE_SERVICE_PRINCIPAL_SECRET="$SP_SECRET"

echo "==> Service principal credentials written to $ENV_FILE."
echo "    Run 'bash infra/setup_node.sh' on each on-prem server to register it."

echo "==> Done."
