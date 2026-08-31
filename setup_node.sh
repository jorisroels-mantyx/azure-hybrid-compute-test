#!/usr/bin/env bash
# setup_node.sh — Install the Azure Batch node agent on an on-prem server.
#
# This registers the machine with your Azure Batch pool so it can
# pick up tasks alongside cloud nodes. No sudo required — installs to
# ~/.local/azure-batch-agent and runs as a systemd user service.
#
# Prerequisites:
#   - Ubuntu 22.04 (other distros need a different node agent SKU)
#   - Network connectivity to Azure (via VPN or public internet)
#   - curl, jq, and .NET 8 runtime already installed
#
# Usage:
#   export BATCH_ACCOUNT_NAME="hybridbatch001"
#   export BATCH_ACCOUNT_URL="hybridbatch001.swedencentral.batch.azure.com"
#   export BATCH_ACCOUNT_KEY="<key>"
#   export BATCH_POOL_ID="hybrid-pool"
#   bash setup_node.sh

set -euo pipefail

: "${BATCH_ACCOUNT_NAME:?Set BATCH_ACCOUNT_NAME}"
: "${BATCH_ACCOUNT_URL:?Set BATCH_ACCOUNT_URL}"
: "${BATCH_ACCOUNT_KEY:?Set BATCH_ACCOUNT_KEY}"
: "${BATCH_POOL_ID:?Set BATCH_POOL_ID}"

NODE_AGENT_VERSION="1.11"  # Update to latest stable as needed
AGENT_DIR="$HOME/.local/azure-batch-agent"
mkdir -p "$AGENT_DIR"

echo "==> Downloading Batch node agent..."
curl -fsSL "https://github.com/Azure/Batch/releases/download/node-agent-${NODE_AGENT_VERSION}/batch-node-agent-linux-x64.tar.gz" \
  | tar -xz -C "$AGENT_DIR"

echo "==> Configuring node agent..."
cat > "$AGENT_DIR/config.json" <<EOF
{
  "accountName": "$BATCH_ACCOUNT_NAME",
  "accountUrl": "https://$BATCH_ACCOUNT_URL",
  "accountKey": "$BATCH_ACCOUNT_KEY",
  "poolId": "$BATCH_POOL_ID",
  "nodeAgentSku": "batch.node.ubuntu 22.04"
}
EOF

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/azure-batch-agent.service" <<EOF
[Unit]
Description=Azure Batch Node Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$AGENT_DIR
ExecStart=$AGENT_DIR/batch-node-agent
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now azure-batch-agent

echo "==> Done. Node should appear in pool '$BATCH_POOL_ID' within a minute."
echo "    Check status: systemctl --user status azure-batch-agent"
echo "    To persist after logout: loginctl enable-linger $USER"
