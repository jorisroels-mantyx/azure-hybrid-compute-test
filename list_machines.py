"""List Arc-connected machines in the resource group.

Required env vars:
    AZURE_SUBSCRIPTION_ID
Optional env vars:
    AZURE_RESOURCE_GROUP  (default: hybrid-arc-rg)
"""

import os

from azure.identity import DefaultAzureCredential
from azure.mgmt.hybridcompute import HybridComputeManagementClient

SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
DEFAULT_RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "hybrid-arc-rg")


def main() -> None:
    client = HybridComputeManagementClient(DefaultAzureCredential(), SUBSCRIPTION_ID)
    machines = list(client.machines.list_by_resource_group(DEFAULT_RESOURCE_GROUP))

    if not machines:
        print("No machines registered.")
        return

    print(f"{'NAME':<24}  {'STATUS':<12}  {'OS':<10}  LOCATION")
    print("─" * 64)
    for m in sorted(machines, key=lambda m: m.name):
        print(f"{m.name:<24}  {m.status:<12}  {(m.os_type or '?'):<10}  {m.location}")


if __name__ == "__main__":
    main()
