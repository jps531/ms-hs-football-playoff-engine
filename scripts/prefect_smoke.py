"""A real Prefect flow run, through Prefect's own engine, as the worker image runs flows.

The unit tests call flow bodies directly with their tasks stubbed, so they never reach the
engine; this does (submitting tasks, waiting on them, retrying, logging), against an ephemeral
Prefect API. CI runs it inside the built worker image:

    docker run --rm -v "$PWD/scripts:/smoke:ro" ci/worker python /smoke/prefect_smoke.py

It's how a library Prefect 2 isn't compatible with (anyio 4.14 was one) shows up before a deploy
instead of in the morning's runs.
"""

import os
import tempfile

os.environ["PREFECT_HOME"] = tempfile.mkdtemp()  # an ephemeral API with its own database
os.environ.pop("PREFECT_API_URL", None)

from prefect import flow, get_run_logger, task  # noqa: E402


@task(retries=1, retry_delay_seconds=0)
def double(x: int) -> int:
    """A task that logs and returns."""
    get_run_logger().info("doubling %s", x)
    return 2 * x


@flow
def smoke() -> list[int]:
    """Submit tasks and wait on them, then call one directly, as the real flows do."""
    futures = [double.submit(i) for i in range(3)]
    return [f.result() for f in futures] + [double(10)]


if __name__ == "__main__":
    result = smoke()
    assert result == [0, 2, 4, 20], result
    print("prefect smoke ok:", result)
