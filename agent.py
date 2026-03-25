"""Skeleton agent logic for SN36 Web Agents.

Returns WaitAction for every request. This is the minimal viable agent
that satisfies the sandbox contract without solving any tasks.
Phase 2 will replace this with real HTML processing and LLM-driven actions.
"""

from loguru import logger


WAIT_ACTION = {"type": "WaitAction", "time_seconds": 1}


async def handle_act(
    task_id: str | None,
    prompt: str | None,
    url: str | None,
    snapshot_html: str | None,
    screenshot: str | None,
    step_index: int | None,
    web_project_id: str | None,
) -> list[dict]:
    """Process an /act request and return a list of actions.

    Skeleton implementation: always returns WaitAction.
    """
    logger.info(
        f"act: step={step_index} project={web_project_id} url={url}"
    )
    return [WAIT_ACTION]
