targetScope = 'subscription'

param location string = 'swedencentral'
param resourceGroupName string = 'hybrid-arc-rg'
param acrName string = 'hybridarccr001'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
}

module resources 'resources.bicep' = {
  name: 'hybrid-arc-resources'
  scope: rg
  params: {
    location: location
    acrName: acrName
  }
}

output acrLoginServer string = resources.outputs.acrLoginServer
