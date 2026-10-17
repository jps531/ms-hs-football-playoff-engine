"""Prefect 2 against the installed libraries: the parts its engine uses on every real flow run.

The flow tests call flow bodies with ``.fn`` and stub the tasks, so they never reach Prefect's
engine; a library Prefect 2 isn't compatible with can pass them all and still crash every
scheduled run. anyio 4.14 did exactly that: it made ``TaskGroup.create_task`` abstract, and
Prefect's ``GatherTaskGroup`` (which every flow uses to wait on its tasks) doesn't define it.
"""

import asyncio

from prefect.utilities.asyncutils import create_gather_task_group, gather


def test_prefect_can_wait_on_task_runs():
    """create_gather_task_group/gather work, as the engine needs to wait on a flow's task runs."""

    async def double(x):
        """A stand-in task body."""
        return 2 * x

    async def run():
        """Create Prefect's task group and gather through it."""
        async with create_gather_task_group() as tg:
            tg.start_soon(double, 1)
        return await gather(lambda: double(2), lambda: double(3))

    assert asyncio.run(run()) == [4, 6]
