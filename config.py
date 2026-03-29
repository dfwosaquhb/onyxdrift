from __future__ import annotations
from urllib.parse import urlsplit
from task_playbooks import TASK_PLAYBOOKS
from website_hints import WEBSITE_HINTS
PORT_TO_PROJECT: dict[int, str] = {8000: 'autocinema', 8001: 'autobooks', 8002: 'autozone', 8003: 'autodining', 8004: 'autocrm', 8005: 'automail', 8006: 'autodelivery', 8007: 'autolodge', 8008: 'autoconnect', 8009: 'autowork', 8010: 'autocalendar', 8011: 'autolist', 8012: 'autodrive', 8013: 'autohealth', 8014: 'autostats', 8015: 'autodiscord'}
SELECTOR_PRIORITY: list[str] = ['id', 'data-testid', 'href', 'aria-label', 'name', 'placeholder', 'title', 'text']
LLM_MODEL = 'gpt-4o-mini'
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 350
PAGE_IR_MAX_TOKENS = 1600
PAGE_IR_CHAR_LIMIT = PAGE_IR_MAX_TOKENS * 4

def detect_website(url: str) -> str | None:
    parts = urlsplit(url)
    port = parts.port
    return PORT_TO_PROJECT.get(port) if port else None
METERING_ENABLED = True
METERING_ENABLED_SHORTCUTS: list[str] = ['login', 'logout', 'registration', 'contact']
METERING_ENABLED_WEBSITES: list[str] = ['autocinema', 'autobooks', 'autozone', 'autodining', 'autocrm', 'automail', 'autolodge', 'autodelivery', 'autowork', 'autoconnect', 'autocalendar', 'autolist', 'autohealth']
METERING_MAX_LLM_ACTIONS: int = 12