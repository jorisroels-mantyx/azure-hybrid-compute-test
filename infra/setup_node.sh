#!/usr/bin/env bash
# Installs the Azure Arc Connected Machine Agent on Ubuntu 22.04.
# Uses outbound HTTPS (443) only — no VPN or router changes needed.
#
# Required env vars:
#   AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_LOCATION, AZURE_TENANT_ID
#   AZURE_SERVICE_PRINCIPAL_ID, AZURE_SERVICE_PRINCIPAL_SECRET, AZURE_ACR_NAME
# Optional:
#   AZURE_ARC_MACHINE_NAME (defaults to hostname)

set -euo pipefail

: "${AZURE_SUBSCRIPTION_ID:?}"
: "${AZURE_RESOURCE_GROUP:?}"
: "${AZURE_LOCATION:?}"
: "${AZURE_TENANT_ID:?}"
: "${AZURE_SERVICE_PRINCIPAL_ID:?}"
: "${AZURE_SERVICE_PRINCIPAL_SECRET:?}"
: "${AZURE_ACR_NAME:?}"
AZURE_ARC_MACHINE_NAME="${AZURE_ARC_MACHINE_NAME:-$(hostname)}"

echo "==> Adding Microsoft package repository..."
curl -fsSL https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb \
  -o /tmp/packages-microsoft-prod.deb
sudo dpkg -i /tmp/packages-microsoft-prod.deb
rm /tmp/packages-microsoft-prod.deb

sudo apt-get update -qq
echo "==> Installing azcmagent..."
sudo apt-get install -y azcmagent

echo "==> Connecting to Azure Arc..."
sudo azcmagent connect \
  --subscription-id          "$AZURE_SUBSCRIPTION_ID" \
  --resource-group           "$AZURE_RESOURCE_GROUP" \
  --location                 "$AZURE_LOCATION" \
  --tenant-id                "$AZURE_TENANT_ID" \
  --service-principal-id     "$AZURE_SERVICE_PRINCIPAL_ID" \
  --service-principal-secret "$AZURE_SERVICE_PRINCIPAL_SECRET" \
  --resource-name            "$AZURE_ARC_MACHINE_NAME" \
  --cloud                    "AzureCloud"

sudo azcmagent show

echo "==> Granting AcrPull to this node's managed identity..."
PRINCIPAL=$(az connectedmachine show \
  --name "$AZURE_ARC_MACHINE_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query identity.principalId -o tsv)
az role assignment create \
  --assignee "$PRINCIPAL" \
  --role AcrPull \
  --scope "$(az acr show --name "$AZURE_ACR_NAME" --query id -o tsv)" \
  --output none

echo "==> Done. Verify: az connectedmachine list --resource-group $AZURE_RESOURCE_GROUP -o table"