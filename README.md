# Azure Hybrid Arc Compute

Run container workloads on on-premises servers managed through Azure Arc — no VPN or router configuration required.

## Architecture

```
Azure                                    On-prem
┌──────────────────────┐                 ┌──────────────────────┐
│  Azure Arc           │   outbound      │  Server (gpu1, ...)  │
│  └─ gpu1, ...        │◄── HTTPS ──────│  ├─ azcmagent        │
│                      │    (port 443)   │  └─ docker           │
│  Azure Container     │                 └──────────────────────┘
│  Registry (ACR)      │
│  └─ train-iris       │
└──────────────────────┘
```

Each on-prem server runs the Azure Arc Connected Machine Agent (`azcmagent`), which opens an outbound HTTPS connection to Azure. No inbound ports, no firewall rules, no router changes needed. Workloads are dispatched from Azure to the nodes via **Arc Run Command**, which pulls a container image from ACR and runs it with `docker run`.

## Prerequisites

- Azure CLI (`az`) authenticated to your subscription
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- On-prem servers running Ubuntu 22.04 with Docker installed and outbound internet access on port 443

## Environment variables

| Variable | Required by | Description |
|---|---|---|
| `AZURE_SUBSCRIPTION_ID` | all | Azure subscription ID |
| `AZURE_LOCATION` | infra, setup_node.sh | Azure region (e.g. `swedencentral`) |
| `AZURE_RESOURCE_GROUP` | all | Resource group for Arc and ACR resources |
| `AZURE_ACR_NAME` | infra, setup_node.sh, submit_job.py | Azure Container Registry name |
| `AZURE_TENANT_ID` | setup_node.sh | AAD tenant ID |
| `AZURE_SERVICE_PRINCIPAL_ID` | setup_node.sh | Service principal app ID for Arc onboarding |
| `AZURE_SERVICE_PRINCIPAL_SECRET` | setup_node.sh | Service principal secret |
| `AZURE_ARC_MACHINE_NAME` | setup_node.sh | Name to register the node as (defaults to hostname) |
| `ACR_USERNAME` | submit_job.py | ACR registry username |
| `ACR_PASSWORD` | submit_job.py | ACR registry password |

Copy `.env.example` to `.env` and fill in your values.

## Setup

### 1. Copy and fill in environment variables, then activate it

```bash
cp .env.example .env
# edit .env with your values
set -a && source .env && set +a
```

### 2. Deploy Azure infrastructure and configure access

```bash
bash infra/setup_infra.sh
```

This deploys the resource group, ACR, and Log Analytics workspace; and creates a service principal for Arc node onboarding, writing its credentials back to `.env`.

### 3. Register on-prem nodes

On each on-prem server (re-source `.env` first so the new SP credentials are in scope):

```bash
set -a && source .env && set +a
bash infra/setup_node.sh
```

Verify registration (from your local machine, after ~2 minutes):

```bash
az connectedmachine list --resource-group "$AZURE_RESOURCE_GROUP" -o table
```

### 4. Build and push the container image

```bash
az acr build \
  --registry "$AZURE_ACR_NAME" \
  --image train-iris:latest \
  ./container
```

### 5. Submit a job

```bash
uv run submit_job.py --image "$AZURE_ACR_NAME.azurecr.io/train-iris:latest"
```

By default the job runs on the first connected node. Use `--machine` to target a specific one:

```bash
uv run submit_job.py --image "$AZURE_ACR_NAME.azurecr.io/train-iris:latest" --machine gpu1
```

If the named machine is not found or not connected, the job falls back to the first available node with a warning.

Additional options:

| Flag | Description |
|---|---|
| `--image IMAGE` | Container image to run (required) |
| `--machine NAME` | Target machine name (optional, falls back to first available) |
| `--job-id ID` | Job ID used in the run command name (defaults to a timestamp) |
| `--no-wait` | Submit without waiting for the job to complete |

## Project structure

```
infra/
  main.bicep        # Subscription-scoped entry point
  resources.bicep   # Azure resource definitions
  main.bicepparam   # Deployment parameters
  setup_infra.sh    # Deploys infrastructure and creates the Arc onboarding service principal
  setup_node.sh     # Installs the Arc agent, connects the node, and grants it AcrPull
container/
  Dockerfile        # Container image definition
  train.py          # Training script (scikit-learn iris example)
submit_job.py       # Dispatches Arc Run Commands to registered nodes
.env.example        # Environment variable template
pyproject.toml      # Python dependencies
```
