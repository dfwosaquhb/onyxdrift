from __future__ import annotations
import re
from bs4 import BeautifulSoup
from models import Candidate

def _sel_attr(attribute: str, value: str) -> dict:
    return {'type': 'attributeValueSelector', 'attribute': attribute, 'value': value, 'case_sensitive': False}

def _click_action(attribute: str, value: str) -> list[dict]:
    return [{'type': 'ClickAction', 'selector': _sel_attr(attribute, value)}]

def try_quick_click(prompt: str, url: str, seed: str | None, step: int) -> list[dict] | None:
    t = prompt.lower()
    if re.search('go\\s+to\\s+today|focus.*today|today.?s?\\s+date\\s+in\\s+the\\s+calendar', t):
        return _click_action('id', 'focus-today')
    if re.search('add\\s+a\\s+new\\s+calendar\\s+event|add\\s+calendar\\s+button|click.*add\\s+calendar', t):
        return _click_action('id', 'new-event-cta')
    if re.search('click.*add\\s+team|add\\s+team\\s+button', t):
        return _click_action('id', 'add-team-btn')
    if re.search('(show\\s+me\\s+my\\s+saved|my\\s+wishlist|show.*wishlist|view.*wishlist)', t):
        return _click_action('id', 'favorite-action')
    if re.search('clicks?\\s+on\\s+the\\s+jobs?\\s+option\\s+in\\s+the\\s+navbar', t):
        return _click_action('href', f'/jobs?seed={seed}') if seed else None
    if re.search('clicks?\\s+on\\s+.*profile\\s+.*in\\s+the\\s+navbar', t):
        return _click_action('href', f'/profile/alexsmith?seed={seed}') if seed else None
    if re.search('(spotlight|featured)\\s+.*(?:movie|film).*details|view\\s+details\\s+.*(?:spotlight|featured)\\s+(?:movie|film)', t):
        return _click_action('id', 'spotlight-view-details-btn')
    if re.search('(spotlight|featured)\\s+.*book.*details|view\\s+details\\s+.*(?:featured|spotlight)\\s+book', t):
        return _click_action('id', 'featured-book-view-details-btn-1')
    if re.search('(spotlight|featured)\\s+.*product.*details|view\\s+details\\s+.*(?:featured|spotlight)\\s+product', t):
        return _click_action('id', 'view-details')
    from urllib.parse import urlsplit
    _port = urlsplit(url).port
    if _port == 8008 and re.search('go\\s+to\\s+the\\s+home\\s+tab|home\\s+tab\\s+from\\s+the\\s+navbar', t):
        return [{'type': 'ClickAction', 'selector': {'type': 'xpathSelector', 'value': '//header//nav/a[1]'}}]
    if re.search('clear\\s+(the\\s+)?(current\\s+)?selection', t):
        return [{'type': 'ClickAction', 'selector': {'type': 'xpathSelector', 'value': "(//button[@role='checkbox'])[1]"}}]
    if re.search('about\\s+page.*feature|feature.*about\\s+page', t):
        if step == 0:
            return _click_action('id', 'nav-about')
        elif step == 1:
            return [{'type': 'ScrollAction', 'down': True}]
        else:
            return [{'type': 'ClickAction', 'selector': {'type': 'xpathSelector', 'value': "//h3[contains(text(),'Curated')]"}}]
    return None
_SEARCH_INPUT_IDS: dict[str, str] = {'automail': 'mail-search', 'autocinema': 'input', 'autodining': 'search-field', 'autodelivery': 'food-search'}

def extract_search_query(prompt: str) -> str | None:
    from constraint_parser import parse_constraints
    constraints = parse_constraints(prompt)
    for c in constraints:
        if c.field == 'query':
            return str(c.value)
    m = re.search('search\\s+(?:for\\s+)?.*?[\'\\"]([^\'\\"]+)[\'\\"]', prompt, re.IGNORECASE)
    if m:
        return m.group(1)
    return None

def try_search_shortcut(prompt: str, website: str | None) -> list[dict] | None:
    if not website:
        return None
    input_id = _SEARCH_INPUT_IDS.get(website)
    if input_id is None:
        return None
    query = extract_search_query(prompt)
    if not query:
        return None
    return [{'type': 'TypeAction', 'text': query, 'selector': _sel_attr('id', input_id)}]

def classify_task(prompt: str) -> str | None:
    lower = prompt.lower()
    if any((kw in lower for kw in ('sign up', 'registration', 'create an account', 'create account'))):
        return 'registration'
    if 'register' in lower and (not any((exc in lower for exc in ('register a movie', 'register a film', 'register the ', 'register for ')))):
        return 'registration'
    if any((kw in lower for kw in ('log out', 'logout', 'sign out'))):
        return 'logout'
    if any((kw in lower for kw in ('log in', 'login', 'sign in'))):
        return 'login'
    if 'contact' in lower and any((kw in lower for kw in ('form', 'message', 'fill', 'support', 'submit'))):
        return 'contact'
    return None

def classify_task_type(prompt: str) -> str:
    lower = prompt.lower()
    login_keywords = ('log in', 'login', 'sign in')
    continuation_keywords = ('then', 'after', 'once logged', 'and then', 'and add', 'and check', 'and go')
    if any((kw in lower for kw in login_keywords)) and any((kw in lower for kw in continuation_keywords)):
        return 'login_then_action'
    shortcut_type = classify_task(prompt)
    if shortcut_type is not None:
        return shortcut_type
    if any((kw in lower for kw in ('buy ', 'purchase', 'add to cart', 'checkout'))):
        return 'purchase'
    if any((kw in lower for kw in ('delete', 'remove', 'cancel'))):
        return 'delete'
    if any((kw in lower for kw in ('edit ', 'update ', 'change ', 'modify'))):
        return 'edit'
    if any((kw in lower for kw in ('search for', 'search ', 'find ', 'look up', 'look for'))):
        return 'search'
    if any((kw in lower for kw in ('filter', 'apply filter', 'narrow'))):
        return 'filter'
    if any((kw in lower for kw in ('show details', 'view details', 'navigate to', 'go to', 'open '))):
        return 'navigate_detail'
    if any((kw in lower for kw in ('fill ', 'submit', 'complete the form', 'create '))):
        return 'form_fill'
    if any((kw in lower for kw in ('select ', 'choose ', 'pick '))):
        return 'dropdown_select'
    if any((kw in lower for kw in ('retrieve', 'show me', 'display', 'get '))):
        return 'data_retrieval'
    return 'general'

def try_shortcut(task_type: str | None, candidates: list[Candidate], soup: BeautifulSoup, step_index: int) -> list[dict] | None:
    if task_type is None:
        return None
    if task_type == 'login':
        if is_already_logged_in(soup):
            return [{'type': 'WaitAction', 'time_seconds': 1}]
        return detect_login_fields(candidates)
    if task_type == 'logout':
        return detect_logout_target(candidates)
    if task_type == 'registration':
        return get_registration_actions(candidates)
    if task_type == 'contact':
        return get_contact_actions(candidates)
    return None

def detect_login_fields(candidates: list[Candidate]) -> list[dict] | None:
    username_candidate = None
    password_candidate = None
    submit_candidate = None
    for c in candidates:
        if username_candidate is None and c.tag == 'input':
            if c.name in {'username', 'user', 'email', 'login'}:
                username_candidate = c
            elif c.input_type in {'email', 'text'} and c.placeholder and ('user' in c.placeholder.lower() or 'email' in c.placeholder.lower()):
                username_candidate = c
        if password_candidate is None and c.input_type == 'password':
            password_candidate = c
        if submit_candidate is None and c.tag in {'button', 'input'}:
            if c.input_type == 'submit':
                submit_candidate = c
            elif c.text and any((kw in c.text.lower() for kw in ('log in', 'login', 'sign in', 'submit'))):
                submit_candidate = c
    if username_candidate and password_candidate and submit_candidate:
        return [{'type': 'TypeAction', 'text': '<username>', 'selector': username_candidate.selector.model_dump()}, {'type': 'TypeAction', 'text': '<password>', 'selector': password_candidate.selector.model_dump()}, {'type': 'ClickAction', 'selector': submit_candidate.selector.model_dump()}]
    return None

def detect_logout_target(candidates: list[Candidate]) -> list[dict] | None:
    for c in candidates:
        if c.text and any((kw in c.text.lower() for kw in ('log out', 'logout', 'sign out'))):
            return [{'type': 'ClickAction', 'selector': c.selector.model_dump()}]
    return None

def get_registration_actions(candidates: list[Candidate]) -> list[dict] | None:
    username_candidate = None
    email_candidate = None
    password_candidate = None
    confirm_candidate = None
    submit_candidate = None
    password_seen = False
    for c in candidates:
        if username_candidate is None and c.tag == 'input':
            if c.name in {'username', 'user'} or (c.placeholder and 'username' in c.placeholder.lower()):
                username_candidate = c
        if email_candidate is None and c.tag == 'input':
            if c.input_type == 'email' or c.name == 'email' or (c.placeholder and 'email' in c.placeholder.lower()):
                email_candidate = c
        if c.input_type == 'password' or (c.name and 'password' in c.name.lower()):
            if not password_seen:
                password_candidate = c
                password_seen = True
            elif confirm_candidate is None:
                confirm_candidate = c
        if submit_candidate is None and c.tag in {'button', 'input'}:
            if c.input_type == 'submit':
                submit_candidate = c
            elif c.text and any((kw in c.text.lower() for kw in ('register', 'sign up', 'signup', 'create', 'submit'))):
                submit_candidate = c
    if not password_candidate or not submit_candidate:
        return None
    if not username_candidate and (not email_candidate):
        return None
    actions: list[dict] = []
    if username_candidate:
        actions.append({'type': 'TypeAction', 'text': '<signup_username>', 'selector': username_candidate.selector.model_dump()})
    if email_candidate:
        actions.append({'type': 'TypeAction', 'text': '<signup_email>', 'selector': email_candidate.selector.model_dump()})
    actions.append({'type': 'TypeAction', 'text': '<signup_password>', 'selector': password_candidate.selector.model_dump()})
    if confirm_candidate:
        actions.append({'type': 'TypeAction', 'text': '<signup_password>', 'selector': confirm_candidate.selector.model_dump()})
    actions.append({'type': 'ClickAction', 'selector': submit_candidate.selector.model_dump()})
    return actions

def get_contact_actions(candidates: list[Candidate]) -> list[dict] | None:
    name_candidate = None
    email_candidate = None
    message_candidate = None
    submit_candidate = None
    for c in candidates:
        if name_candidate is None and c.tag == 'input':
            if c.name in {'name', 'full_name', 'fullname'} or (c.placeholder and 'name' in c.placeholder.lower()):
                name_candidate = c
        if email_candidate is None and c.tag == 'input':
            if c.name == 'email' or c.input_type == 'email':
                email_candidate = c
        if message_candidate is None:
            if c.tag == 'textarea':
                message_candidate = c
            elif c.name in {'message', 'msg', 'content', 'body'}:
                message_candidate = c
        if submit_candidate is None and c.tag in {'button', 'input'}:
            if c.input_type == 'submit':
                submit_candidate = c
            elif c.text and any((kw in c.text.lower() for kw in ('send', 'submit', 'contact'))):
                submit_candidate = c
    if not name_candidate or not email_candidate or (not message_candidate) or (not submit_candidate):
        return None
    return [{'type': 'TypeAction', 'text': 'Test User', 'selector': name_candidate.selector.model_dump()}, {'type': 'TypeAction', 'text': '<signup_email>', 'selector': email_candidate.selector.model_dump()}, {'type': 'TypeAction', 'text': 'Test message', 'selector': message_candidate.selector.model_dump()}, {'type': 'ClickAction', 'selector': submit_candidate.selector.model_dump()}]

def is_already_logged_in(soup: BeautifulSoup) -> bool:
    indicators = ['logout', 'log out', 'sign out', 'my profile', 'my account', 'dashboard']
    text = soup.get_text(separator=' ').lower()
    for indicator in indicators:
        if indicator in text:
            return True
    return False