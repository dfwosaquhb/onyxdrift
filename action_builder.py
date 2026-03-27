from __future__ import annotations
import json
import re
import logging
logger = logging.getLogger(__name__)
from models import Candidate
from navigation import preserve_seed, is_localhost_url, normalize_url
_WAIT_ACTION = {'type': 'WaitAction', 'time_seconds': 1}

def parse_llm_response(content: str) -> dict | None:
    text = content.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    fence_match = re.search('```(?:json)?\\s*\\n?(.*?)\\n?\\s*```', text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except (json.JSONDecodeError, ValueError):
            pass
    return None

def build_iwa_action(decision: dict, candidates: list[Candidate], current_url: str, seed: str | None) -> dict:
    action_type = decision.get('action', 'wait')
    if action_type in ('click', 'type', 'select_option'):
        candidate_id = decision.get('candidate_id')
        if candidate_id is None or not isinstance(candidate_id, int):
            logger.warning(f'Missing or invalid candidate_id for {action_type}')
            return _WAIT_ACTION
        if candidate_id < 0 or candidate_id >= len(candidates):
            logger.warning(f'candidate_id {candidate_id} out of range (0-{len(candidates) - 1})')
            return _WAIT_ACTION
        candidate = candidates[candidate_id]
        selector_dict = candidate.selector.model_dump()
        if action_type == 'click':
            return {'type': 'ClickAction', 'selector': selector_dict}
        if action_type == 'type':
            text = decision.get('text', decision.get('value', ''))
            text = infer_credentials(text, candidate)
            return {'type': 'TypeAction', 'text': text, 'selector': selector_dict}
        if action_type == 'select_option':
            text = decision.get('text', '')
            return {'type': 'SelectDropDownOptionAction', 'text': text, 'selector': selector_dict}
    if action_type == 'navigate':
        url = decision.get('url', '')
        if not url:
            logger.warning('Navigate action missing URL')
            return _WAIT_ACTION
        if not is_localhost_url(url):
            logger.warning(f'Blocked non-localhost navigate: {url}')
            return _WAIT_ACTION
        final_url = preserve_seed(url, current_url)
        from urllib.parse import urlsplit
        current_parts = urlsplit(current_url)
        final_parts = urlsplit(final_url)
        if current_parts.path == final_parts.path and current_parts.query == final_parts.query:
            logger.info('Same-URL navigation detected, returning ScrollAction instead')
            return {'type': 'ScrollAction', 'down': True}
        return {'type': 'NavigateAction', 'url': final_url}
    if action_type == 'scroll':
        direction = decision.get('direction', 'down')
        if direction == 'up':
            return {'type': 'ScrollAction', 'up': True}
        return {'type': 'ScrollAction', 'down': True}
    return _WAIT_ACTION

def infer_credentials(text: str, candidate: Candidate) -> str:
    if text:
        return text
    if candidate.input_type == 'password':
        return '<password>'
    if candidate.name in {'username', 'user', 'login'}:
        return '<username>'
    if candidate.input_type == 'email' or candidate.name == 'email':
        return '<username>'
    return text