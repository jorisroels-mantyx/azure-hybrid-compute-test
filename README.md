# Azure Hybrid Compute Test

Proof-of-concept lab for testing **Site-to-Site VPN** connectivity between an on-premises network and Azure. A containerised Python script verifies the tunnel by uploading/downloading a blob to Azure Storage.

## What gets deployed

All infrastructure is defined in **Bicep** (`main.bicep` → `resources.bicep`):

- **VNet** (`10.1.0.0/16`) with a Gateway Subnet
- **VPN Gateway** + Local Network Gateway + IPsec connection
- **Storage Account** with a `test-container` blob container
- **Azure Container Registry** (Basic SKU)

## Prerequisites

- Azure CLI (`az`)
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Docker (to build/run the test container)

## Usage

### 1. Deploy infrastructure

```bash
az deployment sub create \
  --location swedencentral \
  --template-file main.bicep \
  --parameters main.bicepparam
```

### 2. Configure on-prem router

Use the `vpnGatewayPublicIp` output and the shared key to set up the IPsec tunnel on your local router/firewall.

### 3. Run the connectivity test

```bash
# Locally
export AZURE_STORAGE_CONNECTION_STRING="<connection-string-from-deployment-output>"
uv run test.py

# Or via Docker
docker build -t hybrid-test .
docker run -e AZURE_STORAGE_CONNECTION_STRING="..." hybrid-test
```

## Project structure

```
main.bicep          # Subscription-scoped entry point (RG + module)
resources.bicep     # All Azure resource definitions
main.bicepparam     # Deployment parameter values
test.py             # Blob upload/download connectivity test
Dockerfile          # Packages test.py (python:3.14-slim + uv)
pyproject.toml      # Python project metadata & dependencies
```
