"""Per-task state tracking for multi-step evaluations (STATE-01 through STATE-04).

Tracks action history, form field state, detects action loops and stuck states.
Uses a module-level dict keyed by task_id (safe because the evaluator calls
/act sequentially per task). Auto-cleanup prevents memory leaks during long runs.
"""

from __future__ import annotations

from models import ActionRecord, TaskState

# Module-level state store: task_id -> TaskState
_TASK_STATES: dict[str, TaskState] = {}


class TaskStateTracker:
    """Static methods for per-task state management across /act calls."""

    @staticmethod
    def get_or_create(task_id: str) -> TaskState:
        """Return existing TaskState or create a new one."""
        if task_id not in _TASK_STATES:
            _TASK_STATES[task_id] = TaskState(task_id=task_id)
        return _TASK_STATES[task_id]

    @staticmethod
    def record_action(
        task_id: str,
        action_type: str,
        selector_value: str | None,
        url: str,
        step_index: int,
    ) -> None:
        """Record an action in the task's history."""
        state = TaskStateTracker.get_or_create(task_id)
        record = ActionRecord(
            action_type=action_type,
            selector_value=selector_value or "",
            url=url,
            step_index=step_index,
        )
        state.history.append(record)

    @staticmethod
    def detect_loop(task_id: str, url: str) -> str | None:
        """Return a warning message if action loop detected, else None.

        Checks if the LAST action (action_type + selector_value + url) appears
        2+ times in history. ScrollAction is excluded from loop detection
        because repeated scrolling is legitimate navigation behavior.
        """
        state = _TASK_STATES.get(task_id)
        if not state or len(state.history) < 2:
            return None

        recent = state.history[-1]

        # Exclude ScrollAction from loop detection (Pitfall 3: scrolling is legitimate)
        if recent.action_type == "ScrollAction":
            return None

        count = sum(
            1
            for h in state.history
            if h.action_type == recent.action_type
            and h.selector_value == recent.selector_value
            and h.url == url
        )
        if count >= 2:
            return (
                f"LOOP DETECTED: You've done '{recent.action_type}' on "
                f"'{recent.selector_value}' at this URL {count} times. "
                f"Try a DIFFERENT action or element."
            )
        return None

    @staticmethod
    def detect_stuck(task_id: str, url: str) -> str | None:
        """Return recovery guidance if stuck for 3+ steps at same URL.

        Triggers when last 3 actions are all at the same URL and use
        2 or fewer unique selectors (indicating no meaningful progress).
        """
        state = _TASK_STATES.get(task_id)
        if not state or len(state.history) < 3:
            return None

        last_3 = state.history[-3:]
        urls = {h.url for h in last_3}
        selectors = {h.selector_value for h in last_3}

        if len(urls) == 1 and len(selectors) <= 2:
            return (
                "STUCK: No progress for 3+ steps. Try: "
                "1) Scroll down to find new elements, "
                "2) Click a different navigation link, "
                "3) Look for an alternative path to complete the task."
            )
        return None

    @staticmethod
    def get_recent_history(task_id: str, count: int = 3) -> list[str]:
        """Return last N actions formatted as human-readable strings for the LLM prompt."""
        state = _TASK_STATES.get(task_id)
        if not state:
            return []
        recent = state.history[-count:]
        return [
            f"Step {r.step_index}: {r.action_type} on '{r.selector_value}' at {r.url}"
            for r in recent
        ]

    @staticmethod
    def record_filled_field(task_id: str, field_name: str) -> None:
        """Record that a form field has been filled."""
        state = TaskStateTracker.get_or_create(task_id)
        state.filled_fields.add(field_name)

    @staticmethod
    def get_filled_fields(task_id: str) -> set[str]:
        """Return the set of filled field names for a task."""
        state = _TASK_STATES.get(task_id)
        return state.filled_fields if state else set()

    @staticmethod
    def cleanup(task_id: str) -> None:
        """Remove state for a completed task to free memory."""
        _TASK_STATES.pop(task_id, None)

    @staticmethod
    def _auto_cleanup(max_kept: int = 5) -> None:
        """Remove oldest task states when store exceeds max_kept.

        Called internally to prevent memory leaks during long evaluation runs.
        Removes oldest entries (by insertion order) down to max_kept.
        """
        while len(_TASK_STATES) > max_kept:
            oldest_key = next(iter(_TASK_STATES))
            del _TASK_STATES[oldest_key]

    @staticmethod
    def _get_all_task_ids() -> list[str]:
        """Return all tracked task IDs (for testing/debugging)."""
        return list(_TASK_STATES.keys())
