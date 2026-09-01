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
| `AZURE_ACR_NAME` | infra, submit_job.py | Azure Container Registry name |
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
source .env
```

### 2. Deploy Azure infrastructure

```bash
az deployment sub create \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location "$AZURE_LOCATION" \
  --template-file main.bicep \
  --parameters main.bicepparam \
  --parameters location="$AZURE_LOCATION" resourceGroupName="$AZURE_RESOURCE_GROUP" acrName="$AZURE_ACR_NAME"
```

This creates the resource group, ACR, and Log Analytics workspace.

### 3. Register on-prem nodes

Create a service principal with the `Azure Connected Machine Onboarding` role:

```bash
az ad sp create-for-rbac \
  --name "arc-onboarding-sp" \
  --role "Azure Connected Machine Onboarding" \
  --scopes "/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$AZURE_RESOURCE_GROUP"
```

Copy the output values into `.env` and export them:

```bash
export AZURE_TENANT_ID=<tenant>
export AZURE_SERVICE_PRINCIPAL_ID=<appId>
export AZURE_SERVICE_PRINCIPAL_SECRET=<password>
```

Then on each on-prem server:

```bash
bash setup_node.sh
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

### 5. Grant the Arc node's identity pull access to ACR

```bash
PRINCIPAL=$(az connectedmachine show \
  --name "$AZURE_ARC_MACHINE_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query identity.principalId -o tsv)

az role assignment create \
  --assignee "$PRINCIPAL" \
  --role AcrPull \
  --scope "$(az acr show --name "$AZURE_ACR_NAME" --query id -o tsv)"
```

### 6. Submit a job

Quick submit — runs the image on all connected nodes:

```bash
uv run submit_job.py --image "$AZURE_ACR_NAME.azurecr.io/train-iris:latest"
```

Or from a job spec YAML:

```bash
uv run submit_job.py job.yaml
```

## Project structure

```
main.bicep          # Subscription-scoped entry point
resources.bicep     # Azure resource definitions
main.bicepparam     # Deployment parameters
container/
  Dockerfile        # Container image definition
  train.py          # Training script (scikit-learn iris example)
submit_job.py       # Dispatches Arc Run Commands to registered nodes
setup_node.sh       # Installs and connects the Arc agent on on-prem servers
job.yaml            # Example job spec
.env.example        # Environment variable template
pyproject.toml      # Python dependencies
```
