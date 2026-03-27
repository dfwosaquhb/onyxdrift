pass
from __future__ import annotations

def build_system_prompt() -> str:
    pass
    return 'You are a web automation agent. You analyze HTML pages and decide browser actions to complete tasks.\n\nOutput format: respond with a single JSON object (no markdown, no explanation).\nKeys:\n  "action": one of "click", "type", "navigate", "scroll", "select_option", "wait"\n  "candidate_id": integer index from the Page Elements list (required for click, type, select_option)\n  "text": string to type or option to select (required for type, select_option)\n  "url": target URL (required for navigate -- must be localhost, must preserve ?seed= parameter)\n  "direction": "up" or "down" (for scroll, default "down")\n\nRules:\n- Only reference candidate_id values that appear in the Page Elements list.\n- For login forms, use <username> and <password> as text values.\n- For navigate actions, always preserve the ?seed= parameter from the current URL.\n- Choose the single most effective action to make progress on the task.\n\nRespond with JSON only. No explanation, no markdown fencing.'

def build_user_prompt(prompt: str, page_ir_text: str, step_index: int, action_history: list[str], website: str | None, website_hint: str='', constraints_block: str='', playbook: str='', loop_warning: str | None=None, stuck_warning: str | None=None, filled_fields: set[str] | None=None) -> str:
    pass
    history_text = '\n'.join((f'  - {h}' for h in action_history)) if action_history else 'None yet'
    parts: list[str] = []
    parts.append(f'TASK: {prompt}')
    website_line = f"WEBSITE: {website or 'unknown'}"
    if website_hint:
        website_line += f' ({website_hint})'
    parts.append(website_line)
    parts.append(f'STEP: {step_index} of 12')
    if constraints_block:
        parts.append('')
        parts.append(constraints_block)
    if playbook:
        parts.append(f'\nPLAYBOOK: {playbook}')
    if loop_warning:
        parts.append(f'\nWARNING: {loop_warning}')
    if stuck_warning:
        parts.append(f'\nWARNING: {stuck_warning}')
    parts.append(f'\nACTION HISTORY:\n{history_text}')
    if filled_fields:
        parts.append(f"\nFILLED FIELDS: {', '.join(sorted(filled_fields))}")
    parts.append(f'\nPAGE ELEMENTS:\n{page_ir_text}')
    parts.append('\nChoose ONE action to make progress on the task. Do NOT repeat previous actions.')
    return '\n'.join(parts)