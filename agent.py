from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
from config import detect_website, WEBSITE_HINTS, TASK_PLAYBOOKS, METERING_ENABLED, METERING_ENABLED_SHORTCUTS, METERING_ENABLED_WEBSITES
from constraint_parser import parse_constraints, format_constraints_block
from html_processing import prune_html, extract_candidates, build_page_ir
from navigation import extract_seed, preserve_seed, is_localhost_url
from shortcuts import classify_task, classify_task_type, try_shortcut, try_quick_click, try_search_shortcut
from state_tracker import TaskStateTracker
from llm_client import LLMClient
from llm_prompts import build_system_prompt, build_user_prompt
from action_builder import parse_llm_response, build_iwa_action
WAIT_ACTION = {'type': 'WaitAction', 'time_seconds': 1}
_llm_client = None

def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client

async def handle_act(task_id: str | None, prompt: str | None, url: str | None, snapshot_html: str | None, screenshot: str | None, step_index: int | None, web_project_id: str | None) -> list[dict]:
    if not prompt or not url:
        logger.warning('Missing prompt or url, returning WaitAction')
        return [WAIT_ACTION]
    step = step_index or 0
    task = task_id or 'unknown'
    website = web_project_id or detect_website(url)
    seed = extract_seed(url)
    state = TaskStateTracker.get_or_create(task)
    if step == 0:
        state.constraints = parse_constraints(prompt)
        state.task_type = classify_task_type(prompt)
        TaskStateTracker._auto_cleanup(max_kept=5)
    quick_actions = try_quick_click(prompt, url, seed, step)
    if quick_actions is not None:
        logger.info(f'Quick click resolved: {len(quick_actions)} actions')
        for (i, qa) in enumerate(quick_actions):
            sel_val = ''
            sel = qa.get('selector', {})
            if isinstance(sel, dict):
                sel_val = sel.get('value', '')
            TaskStateTracker.record_action(task, qa.get('type', ''), sel_val, url, step + i)
        return quick_actions
    search_actions = try_search_shortcut(prompt, website)
    if search_actions is not None:
        logger.info(f'Search shortcut resolved: {len(search_actions)} actions')
        for (i, sa) in enumerate(search_actions):
            sel_val = ''
            sel = sa.get('selector', {})
            if isinstance(sel, dict):
                sel_val = sel.get('value', '')
            TaskStateTracker.record_action(task, sa.get('type', ''), sel_val, url, step + i)
            if sa.get('type') == 'TypeAction' and sel_val:
                TaskStateTracker.record_filled_field(task, sel_val)
        return search_actions
    if snapshot_html and snapshot_html.strip():
        soup = prune_html(snapshot_html)
        candidates = extract_candidates(soup)
    else:
        soup = None
        candidates = []
    shortcut_type = classify_task(prompt)
    if METERING_ENABLED and shortcut_type and (shortcut_type not in METERING_ENABLED_SHORTCUTS):
        shortcut_type = None
    if shortcut_type and soup and candidates:
        shortcut_actions = try_shortcut(shortcut_type, candidates, soup, step)
        if shortcut_actions is not None:
            logger.info(f"Shortcut '{shortcut_type}' resolved: {len(shortcut_actions)} actions")
            for (i, sa) in enumerate(shortcut_actions):
                sel_val = ''
                sel = sa.get('selector', {})
                if isinstance(sel, dict):
                    sel_val = sel.get('value', '')
                TaskStateTracker.record_action(task, sa.get('type', ''), sel_val, url, step + i)
                if sa.get('type') == 'TypeAction' and sel_val:
                    TaskStateTracker.record_filled_field(task, sel_val)
            return shortcut_actions
    if not candidates:
        logger.warning('No candidates extracted, returning WaitAction (page may still be loading)')
        TaskStateTracker.record_action(task, 'WaitAction', '', url, step)
        return [{'type': 'WaitAction', 'time_seconds': 2}]
    page_ir = build_page_ir(soup, url, candidates)
    if METERING_ENABLED and website and (website not in METERING_ENABLED_WEBSITES):
        logger.info(f"Metering: website '{website}' disabled, returning WaitAction")
        return [WAIT_ACTION]
    page_ir_text = page_ir.raw_text
    action_history = TaskStateTracker.get_recent_history(task, count=3)
    loop_warning = TaskStateTracker.detect_loop(task, url)
    stuck_warning = TaskStateTracker.detect_stuck(task, url)
    filled_fields = TaskStateTracker.get_filled_fields(task)
    constraints_block = format_constraints_block(state.constraints)
    website_hint = WEBSITE_HINTS.get(website, '') if website else ''
    playbook = TASK_PLAYBOOKS.get(state.task_type, TASK_PLAYBOOKS.get('general', ''))
    if stuck_warning and step >= 3:
        recent_actions = state.history[-2:] if len(state.history) >= 2 else []
        all_scrolls = all((a.action_type == 'ScrollAction' for a in recent_actions)) if recent_actions else False
        if not all_scrolls:
            logger.info('Stuck recovery: scrolling to discover new elements')
            TaskStateTracker.record_action(task, 'ScrollAction', '', url, step)
            return [{'type': 'ScrollAction', 'down': True}]
    try:
        client = get_llm_client()
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(prompt=prompt, page_ir_text=page_ir_text, step_index=step, action_history=action_history, website=website, website_hint=website_hint, constraints_block=constraints_block, playbook=playbook, loop_warning=loop_warning, stuck_warning=stuck_warning, filled_fields=filled_fields)
        messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]
        llm_response = client.chat(task_id=task, messages=messages)
    except Exception as e:
        logger.error(f'LLM call failed: {e}')
        return [WAIT_ACTION]
    decision = parse_llm_response(llm_response)
    if decision is None:
        logger.warning(f'Failed to parse LLM response: {llm_response[:200]}')
        return [WAIT_ACTION]
    action = build_iwa_action(decision, page_ir.candidates, url, seed)
    action_type = action.get('type', 'unknown')
    if step == 0 and action_type == 'NavigateAction':
        logger.info('Blocked NavigateAction on step 0 — already on correct page, scrolling instead')
        action = {'type': 'ScrollAction', 'down': True}
        action_type = 'ScrollAction'
    logger.info(f'LLM action: {action_type}')
    selector_value = ''
    sel = action.get('selector', {})
    if isinstance(sel, dict):
        selector_value = sel.get('value', '')
    TaskStateTracker.record_action(task, action_type, selector_value, url, step)
    if action_type == 'TypeAction' and selector_value:
        TaskStateTracker.record_filled_field(task, selector_value)
    return [action]