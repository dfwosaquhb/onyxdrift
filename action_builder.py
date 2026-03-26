"""Action building and validation for SN36 Web Agent (LLM-03, LLM-04, SHORT-05).

Parses LLM JSON responses into validated IWA action dicts.
Handles: click, type, navigate, scroll, select_option, wait.
Validates candidate_id against actual candidates, blocks external URLs,
prevents same-URL navigation loops, and infers credential placeholders.
"""

from __future__ import annotations

import json
import re

import logging
logger = logging.getLogger(__name__)

from models import Candidate
from navigation import preserve_seed, is_localhost_url, normalize_url

_WAIT_ACTION = {"type": "WaitAction", "time_seconds": 1}


def parse_llm_response(content: str) -> dict | None:
    """Parse LLM response content into a decision dict.

    Tries in order:
    1. Direct JSON parse
    2. Fence-stripped JSON (```json ... ``` or ``` ... ```)
    3. First { to last } extraction

    Returns None if all parsing attempts fail.
    """
    text = content.strip()

    # Fast path: direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Fence stripping: ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Object extraction: first { to last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def build_iwa_action(
    decision: dict,
    candidates: list[Candidate],
    current_url: str,
    seed: str | None,
) -> dict:
    """Build a validated IWA action dict from an LLM decision.

    Args:
        decision: Parsed LLM response dict with "action", "candidate_id", etc.
        candidates: List of interactive element candidates from the page.
        current_url: The current browser URL (for seed preservation, loop detection).
        seed: Extracted seed value from the task URL.

    Returns:
        An IWA-compatible action dict (e.g., {"type": "ClickAction", "selector": {...}}).
    """
    action_type = decision.get("action", "wait")

    if action_type in ("click", "type", "select_option"):
        candidate_id = decision.get("candidate_id")
        if candidate_id is None or not isinstance(candidate_id, int):
            logger.warning(f"Missing or invalid candidate_id for {action_type}")
            return _WAIT_ACTION

        if candidate_id < 0 or candidate_id >= len(candidates):
            logger.warning(f"candidate_id {candidate_id} out of range (0-{len(candidates) - 1})")
            return _WAIT_ACTION

        candidate = candidates[candidate_id]
        selector_dict = candidate.selector.model_dump()

        if action_type == "click":
            return {"type": "ClickAction", "selector": selector_dict}

        if action_type == "type":
            text = decision.get("text", decision.get("value", ""))
            text = infer_credentials(text, candidate)
            return {"type": "TypeAction", "text": text, "selector": selector_dict}

        if action_type == "select_option":
            text = decision.get("text", "")
            return {"type": "SelectDropDownOptionAction", "text": text, "selector": selector_dict}

    if action_type == "navigate":
        url = decision.get("url", "")
        if not url:
            logger.warning("Navigate action missing URL")
            return _WAIT_ACTION

        # Block external URLs
        if not is_localhost_url(url):
            logger.warning(f"Blocked non-localhost navigate: {url}")
            return _WAIT_ACTION

        # Preserve seed
        final_url = preserve_seed(url, current_url)

        # Prevent same-URL navigation loop
        from urllib.parse import urlsplit

        current_parts = urlsplit(current_url)
        final_parts = urlsplit(final_url)
        if (
            current_parts.path == final_parts.path
            and current_parts.query == final_parts.query
        ):
            logger.info("Same-URL navigation detected, returning ScrollAction instead")
            return {"type": "ScrollAction", "down": True}

        return {"type": "NavigateAction", "url": final_url}

    if action_type == "scroll":
        direction = decision.get("direction", "down")
        if direction == "up":
            return {"type": "ScrollAction", "up": True}
        return {"type": "ScrollAction", "down": True}

    # Default: wait
    return _WAIT_ACTION


def infer_credentials(text: str, candidate: Candidate) -> str:
    """Infer credential placeholders for empty TypeAction text.

    If the LLM returned empty text for a password or username field,
    auto-fill with the appropriate credential placeholder.
    Does NOT override explicit LLM text choices.

    Args:
        text: The text from the LLM decision (may be empty).
        candidate: The target input element candidate.

    Returns:
        The text to use (original, or inferred placeholder).
    """
    # Don't override explicit text
    if text:
        return text

    # Password field -> <password>
    if candidate.input_type == "password":
        return "<password>"

    # Username/email field -> <username>
    if candidate.name in {"username", "user", "login"}:
        return "<username>"
    if candidate.input_type == "email" or candidate.name == "email":
        return "<username>"

    # No inference possible
    return text
