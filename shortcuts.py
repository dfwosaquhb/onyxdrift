"""Deterministic shortcut actions for common task types (SHORT-01 through SHORT-04).

Zero-LLM-cost actions for predictable tasks: LOGIN, LOGOUT, REGISTRATION, CONTACT.
These bypass the LLM entirely for maximum speed and minimum cost.

Credential placeholder protocol:
  - Login: <username>, <password>
  - Registration: <signup_username>, <signup_email>, <signup_password> (NEVER <username>)
  - Contact: uses <signup_email> for email field
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from models import Candidate


def classify_task(prompt: str) -> str | None:
    """Classify a task prompt as a shortcut type or None.

    Returns one of: "registration", "logout", "login", "contact", or None.
    Order matters: check most specific patterns first to avoid false matches.
    """
    lower = prompt.lower()

    # Registration (check before login -- "sign up" must not match "sign in")
    if any(kw in lower for kw in ("sign up", "register", "registration", "create an account", "create account")):
        return "registration"

    # Logout (check before login -- "log out" must not match "log in")
    if any(kw in lower for kw in ("log out", "logout", "sign out")):
        return "logout"

    # Login
    if any(kw in lower for kw in ("log in", "login", "sign in")):
        return "login"

    # Contact form
    if "contact" in lower and any(kw in lower for kw in ("form", "message", "fill")):
        return "contact"

    return None


def classify_task_type(prompt: str) -> str:
    """Classify a task prompt into a broad task type for playbook selection.

    Returns one of: login_then_action, login, logout, registration, contact,
    purchase, delete, edit, search, filter, navigate_detail, form_fill,
    dropdown_select, data_retrieval, or "general" as fallback.

    This is separate from classify_task() which only returns shortcut types.
    classify_task_type() covers ALL task types for LLM playbook hints.
    """
    lower = prompt.lower()

    # 1. login_then_action: prompt has login keywords AND continuation keywords
    login_keywords = ("log in", "login", "sign in")
    continuation_keywords = ("then", "after", "once logged", "and then", "and add", "and check", "and go")
    if any(kw in lower for kw in login_keywords) and any(kw in lower for kw in continuation_keywords):
        return "login_then_action"

    # 2. Delegate to existing classify_task() for shortcut types
    shortcut_type = classify_task(prompt)
    if shortcut_type is not None:
        return shortcut_type

    # 3. purchase
    if any(kw in lower for kw in ("buy ", "purchase", "add to cart", "checkout")):
        return "purchase"

    # 4. delete
    if any(kw in lower for kw in ("delete", "remove", "cancel")):
        return "delete"

    # 5. edit
    if any(kw in lower for kw in ("edit ", "update ", "change ", "modify")):
        return "edit"

    # 6. search
    if any(kw in lower for kw in ("search for", "search ", "find ", "look up", "look for")):
        return "search"

    # 7. filter
    if any(kw in lower for kw in ("filter", "apply filter", "narrow")):
        return "filter"

    # 8. navigate_detail
    if any(kw in lower for kw in ("show details", "view details", "navigate to", "go to", "open ")):
        return "navigate_detail"

    # 9. form_fill
    if any(kw in lower for kw in ("fill ", "submit", "complete the form", "create ")):
        return "form_fill"

    # 10. dropdown_select
    if any(kw in lower for kw in ("select ", "choose ", "pick ")):
        return "dropdown_select"

    # 11. data_retrieval
    if any(kw in lower for kw in ("retrieve", "show me", "display", "get ")):
        return "data_retrieval"

    # 12. Default
    return "general"


def try_shortcut(
    task_type: str | None,
    candidates: list[Candidate],
    soup: BeautifulSoup,
    step_index: int,
) -> list[dict] | None:
    """Try to resolve a task with a deterministic shortcut.

    Returns a list of IWA action dicts, or None to fall through to LLM.
    """
    if task_type is None:
        return None

    if task_type == "login":
        if is_already_logged_in(soup):
            return [{"type": "WaitAction", "time_seconds": 1}]
        return detect_login_fields(candidates)

    if task_type == "logout":
        return detect_logout_target(candidates)

    if task_type == "registration":
        return get_registration_actions(candidates)

    if task_type == "contact":
        return get_contact_actions(candidates)

    return None


def detect_login_fields(candidates: list[Candidate]) -> list[dict] | None:
    """Detect login form fields and return TypeAction + ClickAction sequence.

    Looks for: username input, password input, submit button.
    Returns 3 actions or None if form not found.
    """
    username_candidate = None
    password_candidate = None
    submit_candidate = None

    for c in candidates:
        # Username/email input
        if username_candidate is None and c.tag == "input":
            if c.name in {"username", "user", "email", "login"}:
                username_candidate = c
            elif c.input_type in {"email", "text"} and c.placeholder and (
                "user" in c.placeholder.lower() or "email" in c.placeholder.lower()
            ):
                username_candidate = c

        # Password input
        if password_candidate is None and c.input_type == "password":
            password_candidate = c

        # Submit button
        if submit_candidate is None and c.tag in {"button", "input"}:
            if c.input_type == "submit":
                submit_candidate = c
            elif c.text and any(
                kw in c.text.lower()
                for kw in ("log in", "login", "sign in", "submit")
            ):
                submit_candidate = c

    if username_candidate and password_candidate and submit_candidate:
        return [
            {"type": "TypeAction", "text": "<username>", "selector": username_candidate.selector.model_dump()},
            {"type": "TypeAction", "text": "<password>", "selector": password_candidate.selector.model_dump()},
            {"type": "ClickAction", "selector": submit_candidate.selector.model_dump()},
        ]

    return None


def detect_logout_target(candidates: list[Candidate]) -> list[dict] | None:
    """Detect a logout button/link and return a ClickAction.

    Returns [ClickAction] or None if no logout target found.
    """
    for c in candidates:
        if c.text and any(kw in c.text.lower() for kw in ("log out", "logout", "sign out")):
            return [{"type": "ClickAction", "selector": c.selector.model_dump()}]

    return None


def get_registration_actions(candidates: list[Candidate]) -> list[dict] | None:
    """Build registration form actions using <signup_*> credential placeholders.

    CRITICAL: NEVER uses <username> or <password> -- always <signup_*> variants.
    """
    username_candidate = None
    email_candidate = None
    password_candidate = None
    confirm_candidate = None
    submit_candidate = None
    password_seen = False

    for c in candidates:
        # Username field
        if username_candidate is None and c.tag == "input":
            if c.name in {"username", "user"} or (
                c.placeholder and "username" in c.placeholder.lower()
            ):
                username_candidate = c

        # Email field
        if email_candidate is None and c.tag == "input":
            if c.input_type == "email" or c.name == "email" or (
                c.placeholder and "email" in c.placeholder.lower()
            ):
                email_candidate = c

        # Password fields (first = password, second = confirm)
        if c.input_type == "password" or (c.name and "password" in c.name.lower()):
            if not password_seen:
                password_candidate = c
                password_seen = True
            elif confirm_candidate is None:
                confirm_candidate = c

        # Submit button
        if submit_candidate is None and c.tag in {"button", "input"}:
            if c.input_type == "submit":
                submit_candidate = c
            elif c.text and any(
                kw in c.text.lower()
                for kw in ("register", "sign up", "signup", "create", "submit")
            ):
                submit_candidate = c

    # Need at least username or email + password + submit
    if not password_candidate or not submit_candidate:
        return None
    if not username_candidate and not email_candidate:
        return None

    actions: list[dict] = []

    if username_candidate:
        actions.append({
            "type": "TypeAction",
            "text": "<signup_username>",
            "selector": username_candidate.selector.model_dump(),
        })

    if email_candidate:
        actions.append({
            "type": "TypeAction",
            "text": "<signup_email>",
            "selector": email_candidate.selector.model_dump(),
        })

    actions.append({
        "type": "TypeAction",
        "text": "<signup_password>",
        "selector": password_candidate.selector.model_dump(),
    })

    if confirm_candidate:
        actions.append({
            "type": "TypeAction",
            "text": "<signup_password>",
            "selector": confirm_candidate.selector.model_dump(),
        })

    actions.append({
        "type": "ClickAction",
        "selector": submit_candidate.selector.model_dump(),
    })

    return actions


def get_contact_actions(candidates: list[Candidate]) -> list[dict] | None:
    """Build contact form actions.

    Fills name, email, message fields and clicks submit.
    """
    name_candidate = None
    email_candidate = None
    message_candidate = None
    submit_candidate = None

    for c in candidates:
        # Name field
        if name_candidate is None and c.tag == "input":
            if c.name in {"name", "full_name", "fullname"} or (
                c.placeholder and "name" in c.placeholder.lower()
            ):
                name_candidate = c

        # Email field
        if email_candidate is None and c.tag == "input":
            if c.name == "email" or c.input_type == "email":
                email_candidate = c

        # Message textarea/input
        if message_candidate is None:
            if c.tag == "textarea":
                message_candidate = c
            elif c.name in {"message", "msg", "content", "body"}:
                message_candidate = c

        # Submit button
        if submit_candidate is None and c.tag in {"button", "input"}:
            if c.input_type == "submit":
                submit_candidate = c
            elif c.text and any(
                kw in c.text.lower()
                for kw in ("send", "submit", "contact")
            ):
                submit_candidate = c

    if not name_candidate or not email_candidate or not message_candidate or not submit_candidate:
        return None

    return [
        {"type": "TypeAction", "text": "Test User", "selector": name_candidate.selector.model_dump()},
        {"type": "TypeAction", "text": "<signup_email>", "selector": email_candidate.selector.model_dump()},
        {"type": "TypeAction", "text": "Test message", "selector": message_candidate.selector.model_dump()},
        {"type": "ClickAction", "selector": submit_candidate.selector.model_dump()},
    ]


def is_already_logged_in(soup: BeautifulSoup) -> bool:
    """Check if the page indicates the user is already logged in.

    Looks for logout links/buttons and profile indicators.
    """
    indicators = ["logout", "log out", "sign out", "my profile", "my account", "dashboard"]
    text = soup.get_text(separator=" ").lower()

    for indicator in indicators:
        if indicator in text:
            return True

    return False
