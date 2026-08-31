# Azure Hybrid Arc Compute

Run workloads on on-premises servers managed through Azure Arc — no VPN or router configuration required.

## Architecture

```
Azure                                    On-prem
┌──────────────────────┐                 ┌──────────────────────┐
│  Azure Arc           │   outbound      │  Server A            │
│  ├─ onprem-node-01   │◄── HTTPS ──────│  └─ azcmagent        │
│  ├─ onprem-node-02   │    (port 443)   │                      │
│  │                   │                 │  Server B            │
│  Storage Account     │                 │  └─ azcmagent        │
│  ├─ arc-input/       │                 └──────────────────────┘
│  └─ arc-output/      │
│  Log Analytics       │
└──────────────────────┘
```

Each on-prem server runs the Azure Arc Connected Machine Agent (`azcmagent`), which opens an outbound HTTPS connection to Azure. No inbound ports, no firewall rules, no router changes needed. Workloads are dispatched from Azure to the nodes via **Arc Run Command**.

## Prerequisites

- Azure CLI (`az`) authenticated to your subscription
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- On-prem servers running Ubuntu 22.04 with outbound internet access on port 443

## Usage

### 1. Deploy Azure infrastructure

```bash
az deployment sub create \
  --location swedencentral \
  --template-file main.bicep \
  --parameters main.bicepparam
```

This creates:
- VNet (for future Azure-side resources)
- Storage account (arc-input / arc-output containers)
- Log Analytics workspace (Arc telemetry)

### 2. Register on-prem nodes

Create a service principal with the `Azure Connected Machine Onboarding` role:

```bash
az ad sp create-for-rbac \
  --name "arc-onboarding-sp" \
  --role "Azure Connected Machine Onboarding" \
  --scopes "/subscriptions/<subscription-id>/resourceGroups/hybrid-arc-rg"
```

Then on each on-prem server:

```bash
export ARC_SUBSCRIPTION_ID="<subscription-id>"
export ARC_RESOURCE_GROUP="hybrid-arc-rg"
export ARC_LOCATION="swedencentral"
export ARC_TENANT_ID="<tenant-id>"
export ARC_SERVICE_PRINCIPAL_ID="<appId>"
export ARC_SERVICE_PRINCIPAL_SECRET="<password>"
export ARC_MACHINE_NAME="onprem-node-01"   # unique per machine

bash setup_node.sh
```

Verify registration (from local machine, after ~2 minutes):

```bash
az connectedmachine list --resource-group hybrid-arc-rg -o table
```

### 3. Submit a job

```bash
export AZURE_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
export ARC_RESOURCE_GROUP="hybrid-arc-rg"
export ARC_SCRIPT='echo "Hello from $(hostname)"'   # your workload here

uv run submit_job.py
```

The script discovers all Connected Arc machines in the resource group, runs the script on each, and reports the results.

## Project structure

```
main.bicep          # Subscription-scoped entry point
resources.bicep     # Azure resource definitions (VNet, Storage, Log Analytics)
main.bicepparam     # Deployment parameters
submit_job.py       # Dispatches Arc Run Commands to registered nodes
setup_node.sh       # Installs and connects the Arc agent on on-prem servers
pyproject.toml      # Python dependencies
```
