from __future__ import annotations
from models import ActionRecord, TaskState
_TASK_STATES: dict[str, TaskState] = {}

class TaskStateTracker:

    @staticmethod
    def get_or_create(task_id: str) -> TaskState:
        if task_id not in _TASK_STATES:
            _TASK_STATES[task_id] = TaskState(task_id=task_id)
        return _TASK_STATES[task_id]

    @staticmethod
    def record_action(task_id: str, action_type: str, selector_value: str | None, url: str, step_index: int) -> None:
        state = TaskStateTracker.get_or_create(task_id)
        record = ActionRecord(action_type=action_type, selector_value=selector_value or '', url=url, step_index=step_index)
        state.history.append(record)

    @staticmethod
    def detect_loop(task_id: str, url: str) -> str | None:
        state = _TASK_STATES.get(task_id)
        if not state or len(state.history) < 2:
            return None
        recent = state.history[-1]
        if recent.action_type == 'ScrollAction':
            return None
        count = sum((1 for h in state.history if h.action_type == recent.action_type and h.selector_value == recent.selector_value and (h.url == url)))
        if count >= 2:
            return f"LOOP DETECTED: You've done '{recent.action_type}' on '{recent.selector_value}' at this URL {count} times. Try a DIFFERENT action or element."
        return None

    @staticmethod
    def detect_stuck(task_id: str, url: str) -> str | None:
        state = _TASK_STATES.get(task_id)
        if not state or len(state.history) < 3:
            return None
        last_3 = state.history[-3:]
        urls = {h.url for h in last_3}
        selectors = {h.selector_value for h in last_3}
        if len(urls) == 1 and len(selectors) <= 2:
            return 'STUCK: No progress for 3+ steps. Try: 1) Scroll down to find new elements, 2) Click a different navigation link, 3) Look for an alternative path to complete the task.'
        return None

    @staticmethod
    def get_recent_history(task_id: str, count: int=3) -> list[str]:
        state = _TASK_STATES.get(task_id)
        if not state:
            return []
        recent = state.history[-count:]
        return [f"Step {r.step_index}: {r.action_type} on '{r.selector_value}' at {r.url}" for r in recent]

    @staticmethod
    def count_consecutive_wait_actions(task_id: str) -> int:
        state = _TASK_STATES.get(task_id)
        if not state or not state.history:
            return 0
        count = 0
        for record in reversed(state.history):
            if record.action_type == 'WaitAction':
                count += 1
            else:
                break
        return count

    @staticmethod
    def record_filled_field(task_id: str, field_name: str) -> None:
        state = TaskStateTracker.get_or_create(task_id)
        state.filled_fields.add(field_name)

    @staticmethod
    def get_filled_fields(task_id: str) -> set[str]:
        state = _TASK_STATES.get(task_id)
        return state.filled_fields if state else set()

    @staticmethod
    def store_prev_candidates(task_id: str, candidates: list) -> None:
        state = TaskStateTracker.get_or_create(task_id)
        state.prev_candidates = candidates

    @staticmethod
    def get_prev_candidates(task_id: str) -> list | None:
        state = _TASK_STATES.get(task_id)
        return state.prev_candidates if state else None

    @staticmethod
    def store_memory(task_id: str, memory, next_goal) -> None:
        state = TaskStateTracker.get_or_create(task_id)
        state.memory = memory if isinstance(memory, str) else ''
        state.next_goal = next_goal if isinstance(next_goal, str) else ''

    @staticmethod
    def get_memory(task_id: str) -> tuple[str, str]:
        state = _TASK_STATES.get(task_id)
        if state is None:
            return ('', '')
        return (state.memory, state.next_goal)

    @staticmethod
    def compute_state_delta(task_id: str, url: str, page_summary: str, dom_digest: str, candidates: list) -> str:
        state = TaskStateTracker.get_or_create(task_id)
        cur_sig_set: set[str] = set()
        for c in (candidates or [])[:30]:
            try:
                sel_val = c.selector.value if hasattr(c, 'selector') and hasattr(c.selector, 'value') else ''
                txt = (c.text or '')[:80] if hasattr(c, 'text') else ''
                cur_sig_set.add(f'{sel_val}|{txt}')
            except Exception:
                continue
        url_changed = state.prev_url != url if state.prev_url else 'unknown'
        summary_changed = state.prev_summary != page_summary if state.prev_summary else 'unknown'
        digest_changed = state.prev_digest != dom_digest if state.prev_digest else 'unknown'
        if state.prev_sig_set:
            added = len(cur_sig_set - state.prev_sig_set)
            removed = len(state.prev_sig_set - cur_sig_set)
            unchanged = len(cur_sig_set & state.prev_sig_set)
        else:
            added = len(cur_sig_set)
            removed = 0
            unchanged = 0
        state.prev_url = url
        state.prev_summary = page_summary
        state.prev_digest = dom_digest
        state.prev_sig_set = cur_sig_set
        return f'url_changed={url_changed}, +{added} new, -{removed} removed, {unchanged} unchanged'

    @staticmethod
    def cleanup(task_id: str) -> None:
        _TASK_STATES.pop(task_id, None)

    @staticmethod
    def _auto_cleanup(max_kept: int=5) -> None:
        while len(_TASK_STATES) > max_kept:
            oldest_key = next(iter(_TASK_STATES))
            del _TASK_STATES[oldest_key]

    @staticmethod
    def _get_all_task_ids() -> list[str]:
        return list(_TASK_STATES.keys())