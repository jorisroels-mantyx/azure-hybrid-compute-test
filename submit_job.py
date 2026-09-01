"""Submit a container job to Arc-enabled on-prem servers via Azure Arc Run Command.

Runs `docker run <image>` on the single connected Arc machine in the resource group.

Required env vars:
    AZURE_SUBSCRIPTION_ID
Optional env vars:
    AZURE_RESOURCE_GROUP  (default: hybrid-arc-rg)
"""

import argparse
import datetime
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum

from azure.identity import DefaultAzureCredential
from azure.mgmt.hybridcompute import HybridComputeManagementClient
from azure.mgmt.hybridcompute.models import MachineRunCommand, MachineRunCommandScriptSource

SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
DEFAULT_RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "hybrid-arc-rg")


# ── Data model ────────────────────────────────────────────────────────────────

class JobState(str, Enum):
    ACTIVE    = "active"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class JobResult:
    job_id: str
    run_id: str
    machine: str
    state: JobState = JobState.ACTIVE
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


# ── Arc helpers ───────────────────────────────────────────────────────────────

def get_client() -> HybridComputeManagementClient:
    return HybridComputeManagementClient(DefaultAzureCredential(), SUBSCRIPTION_ID)


def discover_machine(client: HybridComputeManagementClient, rg: str, name: str | None = None) -> str:
    machines = list(client.machines.list_by_resource_group(rg))
    connected = [m.name for m in machines if m.status == "Connected"]
    if not connected:
        print("No connected Arc machines found.", file=sys.stderr)
        sys.exit(1)
    if name:
        if name in connected:
            print(f"Machine: {name}")
            return name
        print(f"Warning: machine '{name}' not found or not connected, falling back to {connected[0]}", file=sys.stderr)
    print(f"Machine: {connected[0]}")
    return connected[0]


def build_docker_script(image: str) -> str:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]

    # Auto-login to ACR when the image is hosted there
    if ".azurecr.io" in image:
        registry = image.split("/")[0]
        acr_user = os.environ.get("ACR_USERNAME", "")
        acr_pass = os.environ.get("ACR_PASSWORD", "")
        if acr_user and acr_pass:
            lines += [
                f"echo '{acr_pass}' | docker login {registry} -u '{acr_user}' --password-stdin",
                "",
            ]

    lines.append(f"docker run --rm {image}")
    return "\n".join(lines)


def submit_run_command(
    client: HybridComputeManagementClient,
    rg: str,
    machine: str,
    cmd_name: str,
    image: str,
) -> None:
    location = client.machines.get(rg, machine).location
    cmd = MachineRunCommand(
        location=location,
        source=MachineRunCommandScriptSource(script=build_docker_script(image)),
        async_execution=False,
    )
    client.machine_run_commands.begin_create_or_update(
        resource_group_name=rg,
        machine_name=machine,
        run_command_name=cmd_name,
        run_command_properties=cmd,
    ).result()


def poll_run_command(
    client: HybridComputeManagementClient,
    rg: str,
    machine: str,
    cmd_name: str,
    result: JobResult,
    timeout_seconds: int = 300,
) -> None:
    result.state = JobState.RUNNING
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        rc = client.machine_run_commands.get(rg, machine, cmd_name)
        state = rc.provisioning_state
        if state in ("Succeeded", "Failed", "Canceled"):
            iv = rc.instance_view
            result.stdout = (iv.output or "").strip() if iv else ""
            result.stderr = (iv.error or "").strip() if iv else ""
            result.exit_code = (iv.exit_code or 0) if iv else 0
            result.state = (
                JobState.COMPLETED if result.exit_code == 0 else JobState.FAILED
            )
            return
        print(f"  [{machine}] {state}, waiting...")
        time.sleep(10)
    result.state = JobState.TIMED_OUT
    result.exit_code = -1


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_job(
    client: HybridComputeManagementClient,
    image: str,
    job_id: str,
    machine_name: str | None = None,
    wait: bool = True,
) -> JobResult:
    rg = DEFAULT_RESOURCE_GROUP
    run_id = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    cmd_name = f"arc-{run_id}"

    print(f"Job:    {job_id}")
    print(f"Run ID: {run_id}")

    machine = discover_machine(client, rg, machine_name)
    result = JobResult(job_id=job_id, run_id=run_id, machine=machine)

    print(f"  Submitting → {machine} ...")
    try:
        submit_run_command(client, rg, machine, cmd_name, image)
        result.state = JobState.RUNNING
    except Exception as exc:
        result.state = JobState.FAILED
        result.stderr = str(exc)
        print(f"  Submission failed: {exc}", file=sys.stderr)
        return result

    if wait:
        try:
            poll_run_command(client, rg, machine, cmd_name, result)
        except Exception as exc:
            result.state = JobState.FAILED
            result.stderr = str(exc)

    return result


# ── Output ────────────────────────────────────────────────────────────────────

def print_summary(result: JobResult) -> None:
    sep = "─" * 72
    print(f"\n{sep}")
    print(f"Job: {result.job_id}   Run: {result.run_id}   Node: {result.machine}")
    exit_str = str(result.exit_code) if result.exit_code is not None else "—"
    print(f"State: {result.state.value}   Exit: {exit_str}")
    print(sep)
    if result.stdout:
        print(f"stdout:\n{result.stdout}")
    if result.stderr:
        print(f"stderr:\n{result.stderr}", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="submit_job.py",
        description="Run a container image on an Arc-connected machine",
    )
    p.add_argument("--image", metavar="IMAGE", required=True, help="Container image to run")
    p.add_argument("--machine", metavar="NAME", help="Target machine name (falls back to first available)")
    p.add_argument("--job-id", metavar="ID", help="Job ID (defaults to a timestamp)")
    wait_group = p.add_mutually_exclusive_group()
    wait_group.add_argument("--wait", action="store_true", default=True)
    wait_group.add_argument("--no-wait", dest="wait", action="store_false")
    return p


def main() -> None:
    args = build_parser().parse_args()

    run_ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    job_id = args.job_id or f"job-{run_ts}"

    client = get_client()
    result = run_job(client, args.image, job_id, machine_name=args.machine, wait=args.wait)
    print_summary(result)

    if result.state in (JobState.FAILED, JobState.TIMED_OUT):
        sys.exit(1)


if __name__ == "__main__":
    main()
