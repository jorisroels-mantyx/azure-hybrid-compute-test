"""Submit a test job to the Azure Batch hybrid pool.

This script creates a pool (if it doesn't exist), submits a job with
sample tasks, and waits for completion. On-prem nodes that have joined
the pool will pick up tasks alongside any cloud nodes.
"""

import datetime
import os
import sys
import time

from azure.batch import BatchClient, models
from azure.core.credentials import AzureNamedKeyCredential
from azure.core.exceptions import ResourceNotFoundError

BATCH_ACCOUNT_NAME = os.environ["BATCH_ACCOUNT_NAME"]
BATCH_ACCOUNT_URL = os.environ["BATCH_ACCOUNT_URL"]
BATCH_ACCOUNT_KEY = os.environ["BATCH_ACCOUNT_KEY"]

POOL_ID = "hybrid-pool"
JOB_ID = f"hybrid-job-{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d-%H%M%S')}"
TASK_COUNT = 10


def get_client() -> BatchClient:
    credential = AzureNamedKeyCredential(BATCH_ACCOUNT_NAME, BATCH_ACCOUNT_KEY)
    return BatchClient(endpoint=f"https://{BATCH_ACCOUNT_URL}", credential=credential)


def ensure_pool(client: BatchClient) -> None:
    """Create the hybrid pool if it doesn't already exist."""
    try:
        client.get_pool(POOL_ID)
        print(f"Pool '{POOL_ID}' already exists.")
        return
    except ResourceNotFoundError:
        pass

    pool = models.BatchPoolCreateOptions(
        id=POOL_ID,
        display_name="Hybrid compute pool",
        vm_size="Standard_D2s_v3",
        virtual_machine_configuration=models.VirtualMachineConfiguration(
            image_reference=models.BatchVmImageReference(
                publisher="canonical",
                offer="0001-com-ubuntu-server-jammy",
                sku="22_04-lts",
                version="latest",
            ),
            node_agent_sku_id="batch.node.ubuntu 22.04",
        ),
        target_dedicated_nodes=0,
        target_low_priority_nodes=0,
    )
    client.create_pool(pool=pool)
    print(f"Pool '{POOL_ID}' created (cloud nodes: 0, waiting for on-prem nodes to join).")


def submit_job(client: BatchClient) -> None:
    """Submit a job with sample tasks."""
    job = models.BatchJobCreateOptions(
        id=JOB_ID,
        pool_info=models.BatchPoolInfo(pool_id=POOL_ID),
    )
    client.create_job(job=job)
    print(f"Job '{JOB_ID}' created.")

    tasks = [
        models.BatchTaskCreateOptions(
            id=f"task-{i:03d}",
            command_line=f'/bin/bash -c "echo Processing item {i} on $(hostname); sleep 5; echo Done {i}"',
        )
        for i in range(TASK_COUNT)
    ]
    client.create_tasks(job_id=JOB_ID, task_collection=tasks)
    print(f"Submitted {TASK_COUNT} tasks.")


def wait_for_tasks(client: BatchClient) -> None:
    """Poll until all tasks complete."""
    print("Waiting for tasks to complete...")
    while True:
        tasks = list(client.list_tasks(job_id=JOB_ID))
        completed = sum(1 for t in tasks if t.state == "completed")
        print(f"  {completed}/{len(tasks)} completed", end="\r")
        if completed == len(tasks):
            break
        time.sleep(5)

    print(f"\nAll {len(tasks)} tasks completed.")
    failed = [t for t in tasks if t.execution_info and t.execution_info.exit_code != 0]
    if failed:
        print(f"  ⚠ {len(failed)} task(s) failed.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    client = get_client()
    ensure_pool(client)
    submit_job(client)
    wait_for_tasks(client)


if __name__ == "__main__":
    main()
