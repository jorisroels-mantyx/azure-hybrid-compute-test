# Azure Hybrid Batch Compute

Run Azure Batch jobs across cloud VMs and on-premises servers connected via a Site-to-Site VPN.

## Architecture

```
Azure                                    On-prem (192.168.1.0/24)
┌──────────────────────┐                 ┌──────────────────────┐
│  Batch Account       │   IPsec VPN     │  Server A            │
│  ├─ hybrid-pool      │◄───────────────►│  └─ Batch node agent │
│  │   ├─ cloud nodes  │                 │                      │
│  │   └─ on-prem nodes│                 │  Server B            │
│  Storage Account     │                 │  └─ Batch node agent │
│  ├─ batch-input/     │                 └──────────────────────┘
│  └─ batch-output/    │
└──────────────────────┘
```

Tasks are submitted to the pool; Azure Batch distributes them across all available nodes (cloud and on-prem) automatically.

## Prerequisites

- Azure CLI (`az`)
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- On-prem servers running Ubuntu 22.04 with VPN connectivity

## Usage

### 1. Deploy Azure infrastructure

```bash
az deployment sub create \
  --location swedencentral \
  --template-file main.bicep \
  --parameters main.bicepparam
```

This creates:
- VNet + VPN Gateway (for on-prem connectivity)
- Azure Batch account
- Storage account (input/output containers)

### 2. Configure on-prem router

Point your IPsec tunnel at the `vpnGatewayPublicIp` output using the shared key from `main.bicepparam`.

### 3. Register on-prem nodes

On each on-prem server, run the setup script:

```bash
export BATCH_ACCOUNT_NAME="hybridbatch001"
export BATCH_ACCOUNT_URL="hybridbatch001.swedencentral.batch.azure.com"
export BATCH_ACCOUNT_KEY="<from deployment output or portal>"
export BATCH_POOL_ID="hybrid-pool"

bash setup_node.sh
```

### 4. Submit a test job

```bash
export BATCH_ACCOUNT_NAME="hybridbatch001"
export BATCH_ACCOUNT_URL="hybridbatch001.swedencentral.batch.azure.com"
export BATCH_ACCOUNT_KEY="<key>"

uv run submit_job.py
```

## Project structure

```
main.bicep          # Subscription-scoped entry point
resources.bicep     # Azure resource definitions (VPN, Batch, Storage)
main.bicepparam     # Deployment parameters
submit_job.py       # Creates pool + submits sample tasks
setup_node.sh       # Installs Batch node agent on on-prem servers
pyproject.toml      # Python dependencies
```
