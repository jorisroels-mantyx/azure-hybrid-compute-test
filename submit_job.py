"""Submit container jobs to Arc-enabled on-prem servers via Azure Arc Run Command.

Each task in the job spec runs `docker run <image>` on an Arc-connected machine.
Env vars are baked into the container image; the job spec selects the image and
which nodes to target.

Required env vars:
    AZURE_SUBSCRIPTION_ID
Optional env vars:
    ARC_RESOURCE_GROUP  (default: hybrid-arc-rg)
"""

import argparse
import datetime
import os
import pathlib
import sys
import time
from dataclasses import dataclass, field
from enum import Enum

import yaml
from azure.identity import DefaultAzureCredential
from azure.mgmt.hybridcompute import HybridComputeManagementClient
from azure.mgmt.hybridcompute.models import MachineRunCommand, MachineRunCommandScriptSource

SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
DEFAULT_RESOURCE_GROUP = os.environ.get("ARC_RESOURCE_GROUP", "hybrid-arc-rg")


# ── Data model ────────────────────────────────────────────────────────────────

class TaskState(str, Enum):
    ACTIVE    = "active"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class EnvironmentSetting:
    name: str
    value: str


@dataclass
class TaskSpec:
    id: str
    display_name: str = ""
    image: str = ""
    environment_settings: list[EnvironmentSetting] = field(default_factory=list)
    timeout_seconds: int = 300
    node: str = ""


@dataclass
class PoolConfig:
    resource_group: str = ""
    node_filter: list[str] = field(default_factory=list)


@dataclass
class JobSpec:
    id: str
    display_name: str = ""
    pool: PoolConfig = field(default_factory=PoolConfig)
    tasks: list[TaskSpec] = field(default_factory=list)


@dataclass
class TaskResult:
    task_id: str
    machine_name: str
    cmd_name: str
    state: TaskState = TaskState.ACTIVE
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


@dataclass
class JobResult:
    job_id: str
    run_id: str
    task_results: list[TaskResult] = field(default_factory=list)


# ── Job spec loading ──────────────────────────────────────────────────────────

def load_job_spec(spec_path: pathlib.Path) -> JobSpec:
    raw = yaml.safe_load(spec_path.read_text())
    j = raw["job"]

    pool_raw = j.get("pool", {})
    pool = PoolConfig(
        resource_group=pool_raw.get("resource_group", ""),
        node_filter=pool_raw.get("node_filter") or [],
    )

    tasks: list[TaskSpec] = []
    for t in j.get("tasks", []):
        env = [
            EnvironmentSetting(name=e["name"], value=str(e["value"]))
            for e in t.get("environment_settings", [])
        ]
        tasks.append(TaskSpec(
            id=t["id"],
            display_name=t.get("display_name", ""),
            image=t["image"],
            environment_settings=env,
            timeout_seconds=t.get("timeout_seconds", 300),
            node=t.get("node", ""),
        ))

    return JobSpec(
        id=j["id"],
        display_name=j.get("display_name", ""),
        pool=pool,
        tasks=tasks,
    )


def quick_job_spec(image: str, job_id: str) -> JobSpec:
    return JobSpec(
        id=job_id,
        display_name="Quick submit",
        tasks=[TaskSpec(id="task-001", display_name="Quick task", image=image)],
    )


# ── Task distribution ─────────────────────────────────────────────────────────

def assign_tasks(
    tasks: list[TaskSpec],
    machines: list[str],
) -> list[tuple[TaskSpec, str]]:
    from dataclasses import replace

    assignments: list[tuple[TaskSpec, str]] = []
    pinned = [t for t in tasks if t.node]
    unpinned = [t for t in tasks if not t.node]

    for task in pinned:
        if task.node not in machines:
            print(
                f"Error: task '{task.id}' pinned to '{task.node}' but that node "
                f"is not connected. Connected: {machines}",
                file=sys.stderr,
            )
            sys.exit(1)
        assignments.append((task, task.node))

    if len(unpinned) == 1:
        for machine in machines:
            derived = replace(unpinned[0], id=f"{unpinned[0].id}-{machine}")
            assignments.append((derived, machine))
    else:
        for i, task in enumerate(unpinned):
            assignments.append((task, machines[i % len(machines)]))

    return assignments


# ── Arc helpers ───────────────────────────────────────────────────────────────

def get_client() -> HybridComputeManagementClient:
    return HybridComputeManagementClient(DefaultAzureCredential(), SUBSCRIPTION_ID)


def discover_pool(client: HybridComputeManagementClient, pool: PoolConfig) -> list[str]:
    rg = pool.resource_group or DEFAULT_RESOURCE_GROUP
    machines = list(client.machines.list_by_resource_group(rg))
    connected = [m.name for m in machines if m.status == "Connected"]
    if pool.node_filter:
        connected = [m for m in connected if m in pool.node_filter]
    if not connected:
        print("No connected Arc machines found.", file=sys.stderr)
        sys.exit(1)
    print(f"Pool: {len(connected)} node(s) — {connected}")
    return connected


def build_docker_script(task: TaskSpec) -> str:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    env_flags = "".join(
        f"  -e {e.name}='{e.value.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}' \\\n"
        for e in task.environment_settings
    )
    lines.append(f"docker run --rm \\\n{env_flags}  {task.image}")
    return "\n".join(lines)


def submit_task(
    client: HybridComputeManagementClient,
    rg: str,
    machine: str,
    cmd_name: str,
    task: TaskSpec,
) -> None:
    location = client.machines.get(rg, machine).location
    cmd = MachineRunCommand(
        location=location,
        source=MachineRunCommandScriptSource(script=build_docker_script(task)),
        async_execution=True,
    )
    client.machine_run_commands.begin_create_or_update(
        resource_group_name=rg,
        machine_name=machine,
        run_command_name=cmd_name,
        run_command_properties=cmd,
    ).result()


def poll_task(
    client: HybridComputeManagementClient,
    rg: str,
    machine: str,
    cmd_name: str,
    result: TaskResult,
    timeout_seconds: int,
) -> None:
    result.state = TaskState.RUNNING
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
                TaskState.COMPLETED if result.exit_code == 0 else TaskState.FAILED
            )
            return
        print(f"  [{result.task_id} @ {machine}] {state}, waiting...")
        time.sleep(10)
    result.state = TaskState.TIMED_OUT
    result.exit_code = -1


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_job(
    client: HybridComputeManagementClient,
    spec: JobSpec,
    wait: bool = True,
) -> JobResult:
    rg = spec.pool.resource_group or DEFAULT_RESOURCE_GROUP
    run_id = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")

    print(f"Job:    {spec.id}  ({spec.display_name})")
    print(f"Run ID: {run_id}")

    machines = discover_pool(client, spec.pool)
    assignments = assign_tasks(spec.tasks, machines)
    job_result = JobResult(job_id=spec.id, run_id=run_id)

    # Build (cmd_name → TaskResult) index alongside assignments
    indexed: list[tuple[TaskSpec, str, str, TaskResult]] = []
    for task, machine in assignments:
        cmd_name = f"arc-{run_id}-{task.id}"[:64]
        tr = TaskResult(task_id=task.id, machine_name=machine, cmd_name=cmd_name)
        job_result.task_results.append(tr)
        indexed.append((task, machine, cmd_name, tr))

    for task, machine, cmd_name, tr in indexed:
        print(f"  Submitting '{task.id}' → {machine} ...")
        try:
            submit_task(client, rg, machine, cmd_name, task)
            tr.state = TaskState.RUNNING
        except Exception as exc:
            tr.state = TaskState.FAILED
            tr.stderr = str(exc)
            print(f"  Submission failed: {exc}", file=sys.stderr)

    if not wait:
        return job_result

    for task, machine, cmd_name, tr in indexed:
        if tr.state == TaskState.FAILED:
            continue
        try:
            poll_task(client, rg, machine, cmd_name, tr, task.timeout_seconds)
        except Exception as exc:
            tr.state = TaskState.FAILED
            tr.stderr = str(exc)

    return job_result


# ── Output ────────────────────────────────────────────────────────────────────

def print_summary(result: JobResult) -> None:
    sep = "─" * 72
    print(f"\n{sep}")
    print(f"Job: {result.job_id}   Run: {result.run_id}")
    print(sep)
    print(f"{'TASK ID':<30}  {'NODE':<20}  {'STATE':<10}  {'EXIT':>4}")
    print(sep)
    for tr in result.task_results:
        exit_str = str(tr.exit_code) if tr.exit_code is not None else "—"
        print(f"{tr.task_id:<30}  {tr.machine_name:<20}  {tr.state:<10}  {exit_str:>4}")
    print(sep)

    for tr in result.task_results:
        if tr.stdout or tr.stderr:
            print(f"\n[{tr.task_id} @ {tr.machine_name}]")
            if tr.stdout:
                print(f"  stdout:\n{tr.stdout}")
            if tr.stderr:
                print(f"  stderr:\n{tr.stderr}", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="submit_job.py",
        description="Submit container jobs to Arc-enabled machines (Azure Batch-style UX)",
    )
    p.add_argument(
        "spec",
        nargs="?",
        type=pathlib.Path,
        metavar="JOB_SPEC",
        help="Path to a job spec YAML file (e.g. job.yaml)",
    )
    p.add_argument(
        "--image",
        metavar="IMAGE",
        help="Quick submit: container image to run on all connected nodes",
    )
    p.add_argument("--job-id", metavar="ID", help="Job ID (used in quick-submit mode)")
    wait_group = p.add_mutually_exclusive_group()
    wait_group.add_argument("--wait", action="store_true", default=True)
    wait_group.add_argument("--no-wait", dest="wait", action="store_false")
    return p


def main() -> None:
    args = build_parser().parse_args()

    if args.spec:
        spec = load_job_spec(args.spec)
    elif args.image:
        run_ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
        spec = quick_job_spec(args.image, args.job_id or f"quick-{run_ts}")
    else:
        build_parser().print_help()
        sys.exit(1)

    client = get_client()
    result = run_job(client, spec, wait=args.wait)
    print_summary(result)

    failed = [
        tr for tr in result.task_results
        if tr.state in (TaskState.FAILED, TaskState.TIMED_OUT)
    ]
    if failed:
        print(f"\n{len(failed)} task(s) failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
