targetScope = 'subscription'

@description('Public IP of your office/lab router')
param onpremPublicIp string

@description('IP range of your local network behind the router')
param onpremAddressSpace array = ['192.168.1.0/24']

@secure()
@description('IPsec shared key — enter the same value on your router')
param vpnSharedKey string

param location string = 'swedencentral'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'hybrid-batch-rg'
  location: location
}

module resources 'resources.bicep' = {
  name: 'hybrid-batch-resources'
  scope: rg
  params: {
    location: location
    onpremPublicIp: onpremPublicIp
    onpremAddressSpace: onpremAddressSpace
    vpnSharedKey: vpnSharedKey
  }
}

output vpnGatewayPublicIp string = resources.outputs.vpnGatewayPublicIp
output batchAccountEndpoint string = resources.outputs.batchAccountEndpoint
output batchAccountName string = resources.outputs.batchAccountName
output storageAccountName string = resources.outputs.storageAccountName
output storageAccountKey string = resources.outputs.storageAccountKey
output acrLoginServer string = resources.outputs.acrLoginServer
