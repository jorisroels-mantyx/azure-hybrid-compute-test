param location string
param onpremPublicIp string
param onpremAddressSpace array
@secure()
param vpnSharedKey string

// ── Networking ────────────────────────────────────────────
resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: 'hybrid-batch-vnet'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: ['10.1.0.0/16']
    }
    subnets: [
      {
        name: 'batch-subnet'
        properties: {
          addressPrefix: '10.1.0.0/24'
        }
      }
      {
        name: 'GatewaySubnet'
        properties: {
          addressPrefix: '10.1.255.0/27'
        }
      }
    ]
  }
}

// ── VPN Gateway ───────────────────────────────────────────
resource vpnPip 'Microsoft.Network/publicIPAddresses@2024-01-01' = {
  name: 'hybrid-batch-vpn-pip'
  location: location
  sku: { name: 'Standard' }
  zones: ['1', '2', '3']
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource vpnGw 'Microsoft.Network/virtualNetworkGateways@2024-01-01' = {
  name: 'hybrid-batch-vpn-gw'
  location: location
  properties: {
    gatewayType: 'Vpn'
    vpnType: 'RouteBased'
    sku: {
      name: 'VpnGw1AZ'
      tier: 'VpnGw1AZ'
    }
    ipConfigurations: [
      {
        name: 'vnetGatewayConfig'
        properties: {
          publicIPAddress: { id: vpnPip.id }
          privateIPAllocationMethod: 'Dynamic'
          subnet: { id: vnet.properties.subnets[1].id }
        }
      }
    ]
  }
}

// ── Local Network Gateway ─────────────────────────────────
resource localGw 'Microsoft.Network/localNetworkGateways@2024-01-01' = {
  name: 'hybrid-batch-local-gw'
  location: location
  properties: {
    gatewayIpAddress: onpremPublicIp
    localNetworkAddressSpace: {
      addressPrefixes: onpremAddressSpace
    }
  }
}

// ── VPN Connection ────────────────────────────────────────
resource vpnConn 'Microsoft.Network/connections@2024-01-01' = {
  name: 'hybrid-batch-vpn-conn'
  location: location
  properties: {
    connectionType: 'IPsec'
    virtualNetworkGateway1: {
      id: vpnGw.id
      properties: {}
    }
    localNetworkGateway2: {
      id: localGw.id
      properties: {}
    }
    sharedKey: vpnSharedKey
  }
}

// ── Storage Account (Batch linked storage) ────────────────
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'hybridbatchsa001'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource inputContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'batch-input'
  properties: { publicAccess: 'None' }
}

resource outputContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'batch-output'
  properties: { publicAccess: 'None' }
}

// ── Azure Batch Account ───────────────────────────────────
resource batchAccount 'Microsoft.Batch/batchAccounts@2024-02-01' = {
  name: 'hybridbatch001'
  location: location
  properties: {
    autoStorage: {
      storageAccountId: storageAccount.id
    }
    poolAllocationMode: 'BatchService'
    publicNetworkAccess: 'Enabled'
  }
}

// ── Azure Container Registry ──────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'hybridarccr001'
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: true
  }
}

// ── Outputs ───────────────────────────────────────────────
output vpnGatewayPublicIp string = vpnPip.properties.ipAddress
output batchAccountEndpoint string = batchAccount.properties.accountEndpoint
output batchAccountName string = batchAccount.name
output storageAccountName string = storageAccount.name
output acrLoginServer string = acr.properties.loginServer

@secure()
output storageAccountKey string = storageAccount.listKeys().keys[0].value
