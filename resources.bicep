param location string
param onpremPublicIp string
param onpremAddressSpace array
@secure()
param vpnSharedKey string

// ── Networking ────────────────────────────────────────────
resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: 'hybrid-test-vnet'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: ['10.1.0.0/16']
    }
    subnets: [
      {
        name: 'default'
        properties: {
          addressPrefix: '10.1.0.0/24'
        }
      }
      {
        // Azure reserves this name specifically for VPN gateways — do not rename it.
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
  name: 'hybrid-test-vpn-pip'
  location: location
  sku: {
    name: 'Standard'
  }
  zones: ['1', '2', '3']
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

// VpnGw1AZ is the current required SKU (non-AZ SKUs can no longer
// be created as of November 2025). This takes ~30 min to provision.
resource vpnGw 'Microsoft.Network/virtualNetworkGateways@2024-01-01' = {
  name: 'hybrid-test-vpn-gw'
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
          publicIPAddress: {
            id: vpnPip.id
          }
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: vnet.properties.subnets[1].id
          }
        }
      }
    ]
  }
}

// ── Local Network Gateway ─────────────────────────────────
// Represents your on-prem network from Azure's perspective.
// Tells Azure: "the other end of the tunnel is at this IP,
// and these address ranges live behind it."
resource localGw 'Microsoft.Network/localNetworkGateways@2024-01-01' = {
  name: 'hybrid-test-local-gw'
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
  name: 'hybrid-test-vpn-conn'
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

// ── Storage ───────────────────────────────────────────────
// LRS (Locally Redundant Storage) is the cheapest option — fine for a test.
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'hybridtestsc001'
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'test-container'
  properties: {
    publicAccess: 'None'
  }
}

// ── Container Registry ────────────────────────────────────
// ACR Basic is enough for one test image. adminUserEnabled lets
// you log in with a username/password — simple for a test,
// you'd use managed identity in production.
resource acr 'Microsoft.ContainerRegistries/registries@2023-07-01' = {
  name: 'hybridtestacr001'
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// ── Outputs ───────────────────────────────────────────────
output vpnGatewayPublicIp string = vpnPip.properties.ipAddress
output localGatewayAddressSpace array = localGw.properties.localNetworkAddressSpace.addressPrefixes

@secure()
output storageConnectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

output acrLoginServer string = acr.properties.loginServer
