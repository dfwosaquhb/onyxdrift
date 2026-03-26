"""Agent configuration constants.

Port-to-project mapping, model parameters, selector priority, and token budgets.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Maps sandbox port numbers to demo web project IDs.
# The evaluator runs each demo web on a fixed port (8000-8015).
PORT_TO_PROJECT: dict[int, str] = {
    8000: "autocinema",
    8001: "autobooks",
    8002: "autozone",
    8003: "autodining",
    8004: "autocrm",
    8005: "automail",
    8006: "autolodge",
    8007: "autodelivery",
    8008: "autowork",
    8009: "autoconnect",
    8010: "autocalendar",
    8011: "autolist",
    8012: "autodrive",
    8013: "autohealth",
    8014: "autostats",
    8015: "autodiscord",
}

# Selector priority: prefer stable attributes. NEVER use CSS class (Tailwind breaks Playwright).
SELECTOR_PRIORITY: list[str] = [
    "id",
    "data-testid",
    "href",
    "aria-label",
    "name",
    "placeholder",
    "title",
    "text",
]

# LLM configuration
LLM_MODEL = "gpt-4o-mini"
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 350

# Page IR token budget
PAGE_IR_MAX_TOKENS = 1200
PAGE_IR_CHAR_LIMIT = PAGE_IR_MAX_TOKENS * 4  # ~4800 chars

# Per-website context hints: short description of each demo web's UI patterns.
# Injected into LLM prompt to give the model site-specific navigation context.
WEBSITE_HINTS: dict[str, str] = {
    "autocinema": "Movie booking site. Genre filters, movie cards, showtime selection, seat picker. Login required for watchlist/comments.",
    "autobooks": "Online bookstore. Search bar, genre filters, book cards. Login required for reading list/comments/admin.",
    "autozone": "E-commerce shop. Product cards with prices, category filters, search bar, shopping cart, wishlist.",
    "autodining": "Restaurant discovery. Search, filter by cuisine, restaurant cards, review submission, table reservation.",
    "autocrm": "CRM system. Contact management, lead tracking, deal pipeline. Login required for all actions.",
    "automail": "Email client. Inbox list, email actions (star/archive/delete/forward), templates, pagination, drafts.",
    "autolodge": "Hotel booking site. Search, hotel cards, guest selector, payment methods, reviews, wishlist.",
    "autodelivery": "Food delivery. Restaurant list with pagination, item cart, address management, checkout.",
    "autowork": "Project management. Task boards, team management, role assignment, task creation/editing.",
    "autoconnect": "Social/professional network. Posts, jobs, profiles, company pages, connections. Like buttons have IDs starting with 'post_like_button_p' followed by a number.",
    "autocalendar": "Calendar app. Day/week/month/5-day views, event creation wizard, attendees, search.",
    "autolist": "Task/todo manager. Task lists, team management, priority setting, task creation/deletion.",
    "autodrive": "File storage. File/folder browsing, upload, sharing, search.",
    "autohealth": "Medical portal. Doctor profiles, appointments, medical analysis, contact forms.",
    "autostats": "Analytics dashboard. Charts, data tables, filter controls, export options.",
    "autodiscord": "Chat application. Channels, messages, server management, user search.",
}

# Per-task-type playbook hints: brief guidance for the LLM on typical action sequences.
# Keyed by classify_task_type() return values.
TASK_PLAYBOOKS: dict[str, str] = {
    "login": "Typical steps: Find username and password fields, type credentials, click submit/login button.",
    "logout": "Typical steps: Find logout or sign-out link (often in nav or profile menu), click it.",
    "registration": "Typical steps: Find registration form, fill username/email/password fields, click register/submit.",
    "contact": "Typical steps: Find contact form, fill name/email/message, click send/submit.",
    "login_then_action": "Typical steps: 1) Login first (username, password, submit). 2) Then navigate to the target section. 3) Complete the main action.",
    "search": "Typical steps: Find the search input, type the query exactly as specified, submit search.",
    "navigate_detail": "Typical steps: Browse or search for the item, then click on it to open its detail page.",
    "filter": "Typical steps: Find filter controls (dropdown, checkbox), select the criteria, apply the filter.",
    "purchase": "Typical steps: Find the item, click Add to Cart, go to cart/checkout, complete the order.",
    "form_fill": "Typical steps: Find each form field, fill values exactly as specified in constraints, then submit.",
    "dropdown_select": "Typical steps: Find the dropdown/select element, click to open, choose the matching option.",
    "data_retrieval": "Typical steps: Navigate to the relevant section, find the item matching constraints, click to view details.",
    "edit": "Typical steps: Navigate to the item, click Edit, update the specified fields, save/submit.",
    "delete": "Typical steps: Navigate to the item, click Delete/Remove, confirm if prompted.",
    "general": "Analyze the page elements and task prompt carefully. Choose the most direct action to make progress.",
}


def detect_website(url: str) -> str | None:
    """Detect which demo website a URL belongs to based on its port.

    Returns the project ID (e.g., "autocinema") or None if the port
    is not in the known mapping.
    """
    parts = urlsplit(url)
    port = parts.port
    return PORT_TO_PROJECT.get(port) if port else None


# --- Metering (baked by deploy.sh from deploy-manifest.json) ---
# When METERING_ENABLED is True, agent restricts capability to configured subset.
# Full capability: set METERING_ENABLED = True (default in dev).
METERING_ENABLED = True
METERING_ENABLED_SHORTCUTS: list[str] = ['login', 'logout', 'registration', 'contact']
METERING_ENABLED_WEBSITES: list[str] = ['autocinema', 'autobooks', 'autozone', 'autodining', 'autocrm', 'automail', 'autolodge', 'autodelivery', 'autowork', 'autoconnect', 'autocalendar', 'autolist', 'autohealth']
METERING_MAX_LLM_ACTIONS: int = 12
