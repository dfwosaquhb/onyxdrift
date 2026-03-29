from __future__ import annotations
import json

def format_evaluator_history(history: list[dict] | None, last_n: int=4) -> str:
    if not history:
        return ''
    lines: list[str] = []
    for h in (history or [])[-last_n:]:
        step = h.get('step', '?')
        action = h.get('action', '')
        cid = h.get('candidate_id')
        text = str(h.get('text', '') or '')[:60]
        ok = h.get('exec_ok', True)
        err = h.get('error')
        suffix = 'OK' if ok else f'FAIL:{str(err)[:40]}'
        lines.append(f'{step}.{action} cid={cid} t={text} [{suffix}]')
    return '\n'.join(lines)

def build_system_prompt() -> str:
    return 'You are a web automation agent. Return JSON only (no markdown).\nKeys: action, candidate_id, text, url, evaluation_previous_goal, memory, next_goal.\naction: click|type|select|navigate|scroll_down|scroll_up|send_keys|done.\nclick/type/select: candidate_id=integer from BROWSER_STATE.\nnavigate: url=full URL (keep ?seed=X param).\ndone: only when task is fully completed.\nRULES: Copy values EXACTLY from TASK_CREDENTIALS/TASK_CONSTRAINTS (include trailing spaces).\nequals->type exact value. not_equals->use any OTHER value. contains->find item with that substring.\nnot_contains/not_in->find item WITHOUT that value. greater/less->numeric comparison.\nCREDENTIALS: username/email may have trailing spaces - type them exactly as shown in quotes.\njob_title_contains->type any title CONTAINING that substring.\nMULTI-STEP: complete login first, then the secondary action. Track progress in memory.\nsend_keys: keys=\'Enter\' to submit a form (works on focused element, no candidate_id needed).\nTOOLS: Return {"tool":"<name>","args":{...}} to inspect page. Max 2 tools per step.\nTools: list_cards({max_cards?,max_text?}); search_text({query}); list_links({}); extract_forms({});\n  css_select({selector}); xpath_select({xpath}); visible_text({}); list_candidates({}).'

def build_structured_hints(candidates: list) -> str:
    inputs = []
    clickables = []
    for c in candidates:
        if c.tag in ('input', 'textarea', 'select'):
            inputs.append({'id': c.index, 'kind': c.input_type or c.tag, 'label': c.text[:80], 'name': c.name or '', 'placeholder': c.placeholder or ''})
        else:
            clickables.append({'id': c.index, 'tag': c.tag, 'label': c.text[:80], 'href': (c.href or '')[:100], 'context': c.context[:220]})
    clickables.sort(key=lambda x: len(x.get('context', '')), reverse=True)
    result = {'inputs': inputs, 'clickables': []}
    base = json.dumps(result, ensure_ascii=False)
    for c in clickables[:25]:
        trial = result.copy()
        trial['clickables'] = result['clickables'] + [c]
        serialized = json.dumps(trial, ensure_ascii=False)
        if len(serialized) > 500:
            break
        result = trial
    return json.dumps(result, ensure_ascii=False)

def build_credentials_block(credentials: dict[str, str]) -> str:
    if not credentials:
        return ''
    lines = [f"  {k}: '{v}'" for (k, v) in credentials.items()]
    return '\n'.join(lines)

def build_user_prompt(prompt: str, browser_state_text: str, step_index: int, website: str | None, website_hint: str='', constraints_block: str='', credentials_block: str='', playbook: str='', page_summary: str='', dom_digest_text: str='', cards_text: str='', structured_hints_text: str='', evaluator_history_text: str='', memory: str='', next_goal: str='', state_delta: str='', stuck_hint: str='', filled_fields_text: str='', action_history_text: str='', task_type: str | None=None, url: str | None=None, **kwargs) -> str:
    parts: list[str] = []
    parts.append(f'TASK: {prompt}')
    parts.append(f"SITE:{website or 'unknown'} TYPE:{task_type or 'unknown'} STEP:{step_index} of 10 URL:{url or ''}")
    if website_hint:
        parts.append(f'\nSITE_HINTS: {website_hint[:150]}')
    if credentials_block:
        parts.append(f'\nTASK_CREDENTIALS (use EXACTLY as-is, no modifications - including spaces):\n{credentials_block}')
    if constraints_block:
        parts.append(f'\nTASK_CONSTRAINTS (use these to find the RIGHT item):\n  {constraints_block}')
    if playbook:
        parts.append(f'\n{playbook[:350]}')
    if page_summary:
        parts.append(f'\nPAGE:\n{page_summary[:400]}')
    if dom_digest_text:
        parts.append(f'\nDOM:\n{dom_digest_text[:200]}')
    if cards_text:
        parts.append(f'\nCARDS:\n{cards_text[:600]}')
    if structured_hints_text:
        parts.append(f'\nSTATE:\n{structured_hints_text[:500]}')
    if evaluator_history_text:
        parts.append(f'\nHISTORY:\n{evaluator_history_text}')
    if action_history_text:
        parts.append(f'\nACTION_HISTORY:\n{action_history_text}')
    if stuck_hint:
        parts.append(f'\nHINT: {stuck_hint}')
    if filled_fields_text:
        parts.append(f'\nALREADY_FILLED: {filled_fields_text}')
    parts.append(f'\nMEMORY:\nPREVIOUS MEMORY: {memory}\nPREVIOUS NEXT_GOAL: {next_goal}')
    if state_delta:
        parts.append(f'\nDELTA: {state_delta[:200]}')
    parts.append(f'\nBROWSER_STATE:\n{browser_state_text}')
    parts.append('\nChoose ONE action to make progress. Do NOT repeat previous actions that failed.')
    return '\n'.join(parts)