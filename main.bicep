targetScope = 'subscription'

// ── Parameters ────────────────────────────────────────────
@description('Public IP of your office/lab router')
param onpremPublicIp string

@description('IP range of your local network behind the router')
param onpremAddressSpace array = ['192.168.1.0/24']

@secure()
@description('A secret passphrase — you\'ll enter the same value on your router')
param vpnSharedKey string

param location string = 'swedencentral'

// ── Resource Group ────────────────────────────────────────
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'hybrid-test-rg'
  location: location
}

// Deploy all resources into the resource group
module resources 'resources.bicep' = {
  name: 'hybrid-test-resources'
  scope: rg
  params: {
    location: location
    onpremPublicIp: onpremPublicIp
    onpremAddressSpace: onpremAddressSpace
    vpnSharedKey: vpnSharedKey
  }
}

// ── Outputs ───────────────────────────────────────────────
@description('The Azure side\'s public IP — you give this to your router')
output vpnGatewayPublicIp string = resources.outputs.vpnGatewayPublicIp

@description('Your router\'s address space as Azure sees it')
output localGatewayAddressSpace array = resources.outputs.localGatewayAddressSpace

@description('Connection string for the storage account')
@secure()
output storageConnectionString string = resources.outputs.storageConnectionString

@description('ACR login server URL')
output acrLoginServer string = resources.outputs.acrLoginServer
