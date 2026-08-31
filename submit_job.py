"""Submit workloads to Arc-enabled on-prem servers via Azure Arc Run Command.

For each Connected Arc machine in the resource group, issues a Run Command
(a shell script executed locally by the Arc agent). Polls each command until
completion and prints stdout/stderr.

Required env vars:
    AZURE_SUBSCRIPTION_ID
Optional env vars:
    ARC_RESOURCE_GROUP  (default: hybrid-arc-rg)
    ARC_SCRIPT          (default: inline echo demo)
"""

import datetime
import os
import sys
import time

from azure.identity import DefaultAzureCredential
from azure.mgmt.hybridcompute import HybridComputeManagementClient
from azure.mgmt.hybridcompute.models import MachineRunCommand, MachineRunCommandScriptSource

SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
RESOURCE_GROUP = os.environ.get("ARC_RESOURCE_GROUP", "hybrid-arc-rg")
SCRIPT = os.environ.get(
    "ARC_SCRIPT",
    'echo "Processing on $(hostname) at $(date)"; sleep 3; echo "Done"',
)


def get_client() -> HybridComputeManagementClient:
    return HybridComputeManagementClient(DefaultAzureCredential(), SUBSCRIPTION_ID)


def list_arc_machines(client: HybridComputeManagementClient) -> list[str]:
    machines = list(client.machines.list_by_resource_group(RESOURCE_GROUP))
    connected = [m.name for m in machines if m.status == "Connected"]
    print(f"Found {len(connected)} connected Arc machine(s): {connected}")
    if not connected:
        print("No connected Arc machines found. Register nodes first with setup_node.sh")
        sys.exit(1)
    return connected


def submit_run_command(
    client: HybridComputeManagementClient,
    machine_name: str,
    cmd_name: str,
) -> None:
    location = client.machines.get(RESOURCE_GROUP, machine_name).location
    cmd = MachineRunCommand(
        location=location,
        source=MachineRunCommandScriptSource(script=SCRIPT),
        async_execution=False,
    )
    client.machine_run_commands.begin_create_or_update(
        resource_group_name=RESOURCE_GROUP,
        machine_name=machine_name,
        run_command_name=cmd_name,
        run_command_properties=cmd,
    ).result()


def poll_run_command(
    client: HybridComputeManagementClient,
    machine_name: str,
    cmd_name: str,
    timeout_seconds: int = 300,
) -> int:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        rc = client.machine_run_commands.get(RESOURCE_GROUP, machine_name, cmd_name)
        state = rc.provisioning_state
        if state in ("Succeeded", "Failed", "Canceled"):
            iv = rc.instance_view
            if iv:
                if iv.output:
                    print(f"  [stdout] {iv.output.strip()}")
                if iv.error:
                    print(f"  [stderr] {iv.error.strip()}", file=sys.stderr)
                return iv.exit_code or 0
            return 0
        print(f"  [{machine_name}] state={state}, waiting...")
        time.sleep(10)
    raise TimeoutError(f"Run command on {machine_name} did not finish within {timeout_seconds}s")


def main() -> None:
    client = get_client()
    machines = list_arc_machines(client)

    run_id = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    cmd_names = {m: f"job-{run_id}-{m}" for m in machines}

    for machine_name, cmd_name in cmd_names.items():
        print(f"Submitting Run Command to {machine_name}...")
        submit_run_command(client, machine_name, cmd_name)

    exit_codes: dict[str, int] = {}
    for machine_name, cmd_name in cmd_names.items():
        print(f"Polling {machine_name}...")
        exit_codes[machine_name] = poll_run_command(client, machine_name, cmd_name)

    print("\nResults:")
    failed = []
    for machine_name, code in exit_codes.items():
        status = "OK" if code == 0 else f"FAILED (exit {code})"
        print(f"  {machine_name}: {status}")
        if code != 0:
            failed.append(machine_name)

    if failed:
        print(f"\n{len(failed)} machine(s) failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
