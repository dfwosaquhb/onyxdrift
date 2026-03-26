"""Agent logic for SN36 Web Agents.

Full /act orchestrator pipeline:
  1. Guard: missing prompt/URL -> WaitAction
  2. Detect website from URL port
  3. Extract seed from URL
  4. Initialize/retrieve task state (constraints, type, history)
  5. Prune HTML and extract candidates
  6. Check shortcuts (zero LLM cost path, records in history)
  7. Build Page IR for LLM
  8. Gather state context (history, loop/stuck warnings, filled fields)
  9. Check stuck recovery strategy
  10. Call LLM with enhanced prompt (constraints, hints, playbook, history, warnings)
  11. Parse response and build validated IWA action
  12. Record action in state history
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from config import (
    detect_website,
    WEBSITE_HINTS,
    TASK_PLAYBOOKS,
    METERING_ENABLED,
    METERING_ENABLED_SHORTCUTS,
    METERING_ENABLED_WEBSITES,
)
from constraint_parser import parse_constraints, format_constraints_block
from html_processing import prune_html, extract_candidates, build_page_ir
from navigation import extract_seed, preserve_seed, is_localhost_url
from shortcuts import classify_task, classify_task_type, try_shortcut
from state_tracker import TaskStateTracker
from llm_client import LLMClient
from llm_prompts import build_system_prompt, build_user_prompt
from action_builder import parse_llm_response, build_iwa_action


WAIT_ACTION = {"type": "WaitAction", "time_seconds": 1}

# Module-level LLM client (lazy singleton -- only created on first LLM-path call)
_llm_client = None


def get_llm_client() -> LLMClient:
    """Get or create the singleton LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


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

    Pipeline: guard -> detect -> seed -> state -> prune -> shortcut ->
    Page IR -> state context -> stuck recovery -> LLM -> action -> record
    """
    # Guard: if no prompt or URL, can't do anything meaningful
    if not prompt or not url:
        logger.warning("Missing prompt or url, returning WaitAction")
        return [WAIT_ACTION]

    step = step_index or 0
    task = task_id or "unknown"

    # 1. Detect website from URL port
    website = web_project_id or detect_website(url)

    # 2. Extract seed from URL
    seed = extract_seed(url)

    # 3. Initialize/retrieve task state
    state = TaskStateTracker.get_or_create(task)
    if step == 0:
        # First step: parse constraints and classify task type (cache in state)
        state.constraints = parse_constraints(prompt)
        state.task_type = classify_task_type(prompt)
        # Auto-cleanup old tasks to prevent memory leaks
        TaskStateTracker._auto_cleanup(max_kept=5)

    # 4. Prune HTML and extract candidates (if HTML provided)
    if snapshot_html and snapshot_html.strip():
        soup = prune_html(snapshot_html)
        candidates = extract_candidates(soup)
    else:
        soup = None
        candidates = []

    # 5. Check shortcuts (zero LLM cost path)
    # NAV-03: Shortcuts already return multiple actions per /act call
    # (login=3 actions, registration=4-5 actions, contact=4 actions),
    # satisfying the multi-action return requirement.
    shortcut_type = classify_task(prompt)
    # Metering guard: disable shortcuts not in enabled list
    if METERING_ENABLED and shortcut_type and shortcut_type not in METERING_ENABLED_SHORTCUTS:
        shortcut_type = None
    if shortcut_type and soup and candidates:
        shortcut_actions = try_shortcut(shortcut_type, candidates, soup, step)
        if shortcut_actions is not None:
            logger.info(f"Shortcut '{shortcut_type}' resolved: {len(shortcut_actions)} actions")
            # Record shortcut actions in history for state continuity
            for i, sa in enumerate(shortcut_actions):
                sel_val = ""
                sel = sa.get("selector", {})
                if isinstance(sel, dict):
                    sel_val = sel.get("value", "")
                TaskStateTracker.record_action(task, sa.get("type", ""), sel_val, url, step + i)
                # Track filled fields for TypeAction
                if sa.get("type") == "TypeAction" and sel_val:
                    TaskStateTracker.record_filled_field(task, sel_val)
            return shortcut_actions

    # 6. Build Page IR (need candidates for LLM)
    if not candidates:
        logger.warning("No candidates extracted, returning ScrollAction")
        TaskStateTracker.record_action(task, "ScrollAction", "", url, step)
        return [{"type": "ScrollAction", "down": True}]

    page_ir = build_page_ir(soup, url, candidates)

    # Metering guard: skip LLM for websites not in enabled list
    if METERING_ENABLED and website and website not in METERING_ENABLED_WEBSITES:
        logger.info(f"Metering: website '{website}' disabled, returning WaitAction")
        return [WAIT_ACTION]

    # 7. Format Page IR as text for prompt
    page_ir_text = page_ir.raw_text

    # 8. Gather state context
    action_history = TaskStateTracker.get_recent_history(task, count=3)
    loop_warning = TaskStateTracker.detect_loop(task, url)
    stuck_warning = TaskStateTracker.detect_stuck(task, url)
    filled_fields = TaskStateTracker.get_filled_fields(task)
    constraints_block = format_constraints_block(state.constraints)
    website_hint = WEBSITE_HINTS.get(website, "") if website else ""
    playbook = TASK_PLAYBOOKS.get(state.task_type, TASK_PLAYBOOKS.get("general", ""))

    # 9. Stuck recovery: avoid scroll spam
    if stuck_warning and step >= 3:
        # Check if last 2 history entries are both ScrollAction
        recent_actions = state.history[-2:] if len(state.history) >= 2 else []
        all_scrolls = all(a.action_type == "ScrollAction" for a in recent_actions) if recent_actions else False
        if not all_scrolls:
            # Try scroll as recovery (not already scrolling)
            logger.info("Stuck recovery: scrolling to discover new elements")
            TaskStateTracker.record_action(task, "ScrollAction", "", url, step)
            return [{"type": "ScrollAction", "down": True}]
        # If already scrolling, fall through to LLM with stuck_warning for a different approach

    # 10. Call LLM with enhanced prompt
    try:
        client = get_llm_client()
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(
            prompt=prompt,
            page_ir_text=page_ir_text,
            step_index=step,
            action_history=action_history,
            website=website,
            website_hint=website_hint,
            constraints_block=constraints_block,
            playbook=playbook,
            loop_warning=loop_warning,
            stuck_warning=stuck_warning,
            filled_fields=filled_fields,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        llm_response = client.chat(task_id=task, messages=messages)
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return [WAIT_ACTION]

    # 11. Parse LLM response
    decision = parse_llm_response(llm_response)
    if decision is None:
        logger.warning(f"Failed to parse LLM response: {llm_response[:200]}")
        return [WAIT_ACTION]

    # 12. Build and validate action
    action = build_iwa_action(decision, page_ir.candidates, url, seed)
    action_type = action.get("type", "unknown")
    logger.info(f"LLM action: {action_type}")

    # 13. Record action in state history
    selector_value = ""
    sel = action.get("selector", {})
    if isinstance(sel, dict):
        selector_value = sel.get("value", "")
    TaskStateTracker.record_action(task, action_type, selector_value, url, step)

    # Track filled fields for TypeAction
    if action_type == "TypeAction" and selector_value:
        TaskStateTracker.record_filled_field(task, selector_value)

    return [action]
