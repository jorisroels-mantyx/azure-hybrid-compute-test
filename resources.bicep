param location string
param acrName string

// ── Azure Container Registry ──────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: true
  }
}

// ── Outputs ───────────────────────────────────────────────
output acrLoginServer string = acr.properties.loginServer
