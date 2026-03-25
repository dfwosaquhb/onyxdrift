"""FastAPI agent for SN36 Web Agents subnet.

Sandbox runs: uvicorn main:app --host 0.0.0.0 --port $SANDBOX_AGENT_PORT
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from agent import handle_act, WAIT_ACTION

app = FastAPI(title="SN36 Web Agent")


@app.get("/health")
async def health():
    """Health check endpoint. Must return HTTP < 400."""
    return {"status": "ok"}


@app.post("/act")
async def act(request: Request):
    """Main agent endpoint. Receives browser state, returns actions.

    Request body: {task_id, prompt, url, snapshot_html, screenshot, step_index, web_project_id}
    Response: {actions: [{type: "...", ...}, ...]}
    """
    try:
        body = await request.json()
    except Exception:
        logger.warning("Failed to parse request body, returning WaitAction")
        return {"actions": [WAIT_ACTION]}

    actions = await handle_act(
        task_id=body.get("task_id"),
        prompt=body.get("prompt"),
        url=body.get("url"),
        snapshot_html=body.get("snapshot_html"),
        screenshot=body.get("screenshot"),
        step_index=body.get("step_index"),
        web_project_id=body.get("web_project_id"),
    )
    return {"actions": actions}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler. Returns WaitAction to prevent
    consecutive failure penalty (2+ failures = score 0).

    API-03: Centralized exception handler returning WaitAction on any
    unhandled error.
    """
    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=200,
        content={"actions": [WAIT_ACTION]},
    )
