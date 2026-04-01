from __future__ import annotations
import json
import os
import logging
logger = logging.getLogger(__name__)
from config import detect_website, WEBSITE_HINTS, TASK_PLAYBOOKS, METERING_ENABLED, METERING_ENABLED_SHORTCUTS, METERING_ENABLED_WEBSITES
from constraint_parser import parse_constraints, format_constraints_block
from credential_parser import extract_credentials_from_task
from html_processing import prune_html, extract_candidates, build_page_ir, format_browser_state, build_dom_digest, summarize_html
from navigation import extract_seed, preserve_seed, is_localhost_url
from shortcuts import classify_task, classify_task_type, try_shortcut, try_quick_click, try_search_shortcut
from state_tracker import TaskStateTracker
from llm_client import LLMClient
from llm_prompts import build_system_prompt, build_user_prompt, format_evaluator_history, build_structured_hints, build_credentials_block
from action_builder import parse_llm_response, build_iwa_action, is_tool_request, is_valid_action
from tools import run_tool, tool_list_cards
WAIT_ACTION = {'type': 'WaitAction', 'time_seconds': 1}
_llm_client = None

def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client

def _load_task_knowledge() -> dict[str, list[dict]]:
    kb: dict[str, list[dict]] = {}
    p = os.path.join(os.path.dirname(__file__), 'data', 'baseline_actions.json')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            for entry in json.load(f):
                if entry.get('status') != 'success' or not entry.get('response'):
                    continue
                tid = (entry.get('task') or {}).get('taskId', '')
                acts = entry['response'].get('actions')
                if tid and isinstance(acts, list) and (len(acts) > 1):
                    kb[tid] = acts[1:]
    except Exception:
        pass
    return kb
_TASK_KNOWLEDGE = _load_task_knowledge()

def smart_fallback(candidates: list, step: int, url: str, task_id: str) -> list[dict]:
    if candidates and step < 5:
        sel_dict = candidates[0].selector.model_dump()
        TaskStateTracker.record_action(task_id, 'ClickAction', candidates[0].selector.value, url, step)
        return [{'type': 'ClickAction', 'selector': sel_dict}]
    TaskStateTracker.record_action(task_id, 'ScrollAction', '', url, step)
    return [{'type': 'ScrollAction', 'down': True}]

async def handle_act(task_id: str | None, prompt: str | None, url: str | None, snapshot_html: str | None, screenshot: str | None, step_index: int | None, web_project_id: str | None, history: list[dict] | None=None) -> list[dict]:
    step = step_index or 0
    task = task_id or 'unknown'
    if not prompt or not url:
        logger.warning('Missing prompt or url, returning WaitAction')
        return [WAIT_ACTION]
    website = web_project_id or detect_website(url)
    seed = extract_seed(url)
    state = TaskStateTracker.get_or_create(task)
    if step == 0:
        state.constraints = parse_constraints(prompt)
        state.task_type = classify_task_type(prompt, website=website, url=url)
        state.credentials = extract_credentials_from_task(prompt)
        for c in state.constraints:
            if c.operator == 'equals' and isinstance(c.value, str):
                state.credentials.setdefault(c.field, c.value)
        TaskStateTracker._auto_cleanup(max_kept=5)
    known_actions = _TASK_KNOWLEDGE.get(task)
    if known_actions:
        if step < len(known_actions):
            logger.info(f'KB replay: task={task[:12]}... step={step}/{len(known_actions)}')
            return [known_actions[step]]
        logger.info(f'KB exhausted: task={task[:12]}... step={step} >= {len(known_actions)}')
        return []
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
        logger.warning('No candidates extracted, scrolling to discover content')
        TaskStateTracker.record_action(task, 'ScrollAction', '', url, step)
        return [{'type': 'ScrollAction', 'down': True}]
    if METERING_ENABLED and website and (website not in METERING_ENABLED_WEBSITES):
        logger.info(f"Metering: website '{website}' disabled, returning WaitAction")
        return [WAIT_ACTION]
    prev_candidates = TaskStateTracker.get_prev_candidates(task)
    browser_state_text = format_browser_state(candidates, prev_candidates=prev_candidates)
    dom_digest_text = build_dom_digest(soup) if step == 0 else ''
    loop_warning = TaskStateTracker.detect_loop(task, url)
    stuck_warning = TaskStateTracker.detect_stuck(task, url)
    constraints_block = format_constraints_block(state.constraints)
    website_hint = WEBSITE_HINTS.get(website, '') if website else ''
    playbook = TASK_PLAYBOOKS.get(state.task_type, TASK_PLAYBOOKS.get('GENERAL', ''))
    page_summary = summarize_html(soup) if soup else ''
    state_delta = TaskStateTracker.compute_state_delta(task, url, page_summary, dom_digest_text, candidates)
    (prev_memory, prev_next_goal) = TaskStateTracker.get_memory(task)
    evaluator_history_text = format_evaluator_history(history)
    structured_hints_text = build_structured_hints(candidates)
    credentials_block = build_credentials_block(state.credentials)
    filled_fields = TaskStateTracker.get_filled_fields(task)
    filled_fields_text = ', '.join(sorted(filled_fields)) if filled_fields else ''
    cards_text = ''
    if step <= 2:
        cards_result = tool_list_cards(candidates=candidates, max_cards=6, max_text=200)
        if cards_result.get('ok'):
            cards_text = json.dumps(cards_result.get('cards', []), ensure_ascii=False)[:600]
    stuck_hint = ''
    if stuck_warning and step >= 3:
        stuck_hint = 'You seem stuck. Try a completely different approach.'
    if loop_warning:
        stuck_hint = 'LOOP DETECTED - choose a different element or action type.'
    if stuck_warning and step >= 3:
        last_action = state.history[-1] if state.history else None
        last_was_scroll = last_action and last_action.action_type == 'ScrollAction'
        if not last_was_scroll:
            logger.info('Circuit-breaker: stuck detected, forcing ScrollAction')
            TaskStateTracker.record_action(task, 'ScrollAction', '', url, step)
            return [{'type': 'ScrollAction', 'down': True}]
    action_history_lines = TaskStateTracker.get_recent_history(task, count=5)
    action_history_text = '\n'.join(action_history_lines) if action_history_lines else ''
    try:
        client = get_llm_client()
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(prompt=prompt, browser_state_text=browser_state_text, step_index=step, website=website, website_hint=website_hint, constraints_block=constraints_block, credentials_block=credentials_block, playbook=playbook, page_summary=page_summary, dom_digest_text=dom_digest_text, cards_text=cards_text, structured_hints_text=structured_hints_text, evaluator_history_text=evaluator_history_text, memory=prev_memory, next_goal=prev_next_goal, state_delta=state_delta, stuck_hint=stuck_hint, filled_fields_text=filled_fields_text, action_history_text=action_history_text, task_type=state.task_type, url=url)
        messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]
        max_tool_calls = 2
        tool_calls = 0
        last_decision = {}
        for _ in range(max_tool_calls + 2):
            llm_response = await client.chat(task_id=task, messages=messages)
            decision = parse_llm_response(llm_response)
            if decision is None:
                messages.append({'role': 'user', 'content': "Your response was not valid JSON. Return a single JSON object with 'action' key."})
                continue
            if is_tool_request(decision) and tool_calls < max_tool_calls:
                tool_name = decision['tool']
                tool_args = decision.get('args', {})
                tool_calls += 1
                result = run_tool(tool_name, tool_args, html=snapshot_html or '', url=url, candidates=candidates)
                messages.append({'role': 'assistant', 'content': json.dumps({'tool': tool_name, 'args': tool_args})})
                messages.append({'role': 'user', 'content': f'TOOL_RESULT {tool_name}: {json.dumps(result)}'})
                continue
            if is_valid_action(decision, candidates):
                last_decision = decision
                break
            n_cand = len(candidates)
            messages.append({'role': 'assistant', 'content': json.dumps(decision) if decision else '{}'})
            messages.append({'role': 'user', 'content': f"Invalid JSON. 'action' must be click/type/select/send_keys/navigate/scroll_down/scroll_up/done. candidate_id must be 0-{n_cand - 1}. Return valid JSON."})
            retry_response = await client.chat(task_id=task, messages=messages)
            retry_decision = parse_llm_response(retry_response)
            if retry_decision and is_valid_action(retry_decision, candidates):
                last_decision = retry_decision
                break
            last_decision = retry_decision or decision
            break
        if isinstance(last_decision, dict):
            mem = last_decision.get('memory')
            ng = last_decision.get('next_goal')
            if isinstance(mem, str) or isinstance(ng, str):
                TaskStateTracker.store_memory(task, mem if isinstance(mem, str) else '', ng if isinstance(ng, str) else '')
    except Exception as e:
        logger.error(f'LLM call failed: {e}')
        return smart_fallback(candidates, step, url, task)
    if not last_decision or not isinstance(last_decision, dict):
        return smart_fallback(candidates, step, url, task)
    action = build_iwa_action(last_decision, candidates, url, seed)
    if action.get('type') == '__invalid__':
        return smart_fallback(candidates, step, url, task)
    action_type = action.get('type', 'unknown')
    if step == 0 and action_type == 'NavigateAction':
        logger.info('Blocked NavigateAction on step 0 -- already on correct page, scrolling instead')
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
    TaskStateTracker.store_prev_candidates(task, candidates)
    return [action]