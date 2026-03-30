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
        return _click_action('id', 'save-item')
    if re.search('change\\s+the\\s+application\\s+theme', t):
        return _click_action('id', 'theme-dark-btn')
    if re.search('clicks?\\s+on\\s+the\\s+jobs?\\s+option\\s+in\\s+the\\s+navbar', t):
        return _click_action('href', f'/jobs?seed={seed}') if seed else None
    if re.search('clicks?\\s+on\\s+.*profile\\s+.*in\\s+the\\s+navbar', t):
        return _click_action('href', f'/profile/alexsmith?seed={seed}') if seed else None
    if re.search('clicks?\\s+favorites?\\s+to\\s+view|open\\s+the\\s+favorites?\\s+section|navbar.*favorites?|favorites?.*navbar', t):
        return _click_action('href', f'/favorites?seed={seed}') if seed else None
    if re.search('clicks?\\s+hire\\s+later\\s+to\\s+view|open\\s+the\\s+hire\\s+later\\s+section|navbar.*hire.?later|hire.?later.*navbar', t):
        return _click_action('href', f'/hire-later?seed={seed}') if seed else None
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
    if re.search('(open\\s+my\\s+saved\\s+posts|view\\s+.*saved\\s+(items|posts))', t):
        return [{'type': 'ClickAction', 'selector': {'type': 'tagContainsSelector', 'value': 'Saved'}}]
    if re.search('(show\\s+my\\s+applied\\s+jobs|view\\s+.*applied\\s+to)', t):
        return [{'type': 'ClickAction', 'selector': {'type': 'tagContainsSelector', 'value': 'Applied'}}]
    if re.search('clear\\s+(the\\s+)?(current\\s+)?selection', t):
        return [{'type': 'ClickAction', 'selector': {'type': 'xpathSelector', 'value': "(//button[@role='checkbox'])[1]"}}]
    if re.search('open\\s+the\\s+contact\\s+page', t):
        return _click_action('id', 'nav-contact')
    if re.search('about\\s+page.*feature|feature.*about\\s+page', t):
        if step == 0:
            return _click_action('id', 'nav-about')
        elif step == 1:
            return [{'type': 'ScrollAction', 'down': True}]
        else:
            return [{'type': 'ClickAction', 'selector': {'type': 'xpathSelector', 'value': "//h3[contains(text(),'Curated')]"}}]
    if re.search('go\\s+back\\s+to\\s+(the\\s+)?(all\\s+)?hotels|return\\s+to\\s+.*hotel\\s+(dashboard|listing)', t):
        return [{'type': 'ClickAction', 'selector': {'type': 'tagContainsSelector', 'value': 'All Hotels'}}]
    if re.search('select\\s+(the\\s+)?calendar\\s+(whose|where|that|named)', t):
        if step == 0:
            return [{'type': 'ClickAction', 'selector': {'type': 'xpathSelector', 'value': "(//input[contains(@aria-label,'calendar')])[1]"}}]
        elif step == 1:
            return [{'type': 'ClickAction', 'selector': {'type': 'xpathSelector', 'value': "(//input[contains(@aria-label,'calendar')])[1]"}}]
        return None
    return None
_SEARCH_INPUT_IDS: dict[str, str] = {'automail': 'mail-search', 'autocinema': 'input', 'autodining': 'search-field', 'autodelivery': 'filter-input'}

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

def classify_task_type(prompt: str, website: str | None=None, url: str | None=None) -> str:
    t = (prompt or '').lower()
    if website == 'autostats' and re.search('(add|star|favorite)\\s+.*\\bto\\s+favorites?\\b|favorite\\s+.*subnet', t, re.IGNORECASE):
        return 'FAVORITE_SUBNET'
    if website == 'autostats' and re.search('(send|transfer)\\s+\\d+\\s*(tao|tau|to\\s)', t, re.IGNORECASE):
        return 'TRANSFER_COMPLETE'
    if website == 'autostats' and re.search('disconnect\\s+(your\\s+)?wallet', t, re.IGNORECASE):
        return 'DISCONNECT_WALLET'
    if website == 'autostats' and re.search('connect\\s+(your\\s+)?wallet|connect\\s+with\\s+(polkadot|talisman|subwallet)', t, re.IGNORECASE):
        return 'CONNECT_WALLET_STATS'
    if website == 'autostats' and re.search('buy\\s+\\d+\\s*(tao|tau|alpha)', t, re.IGNORECASE):
        return 'EXECUTE_BUY'
    if website == 'autostats' and re.search('sell\\s+\\d+\\s*(alpha|tao|tau)', t, re.IGNORECASE):
        return 'EXECUTE_SELL'
    if website == 'autostats' and re.search('view\\s+(a\\s+)?subnet', t, re.IGNORECASE):
        return 'VIEW_SUBNET'
    if website == 'autostats' and re.search('view\\s+(a\\s+)?validator', t, re.IGNORECASE):
        return 'VIEW_VALIDATOR'
    if website == 'autostats' and re.search('view\\s+(a\\s+)?block', t, re.IGNORECASE):
        return 'VIEW_BLOCK'
    if website == 'autostats' and re.search('view\\s+(an?\\s+)?account', t, re.IGNORECASE):
        return 'VIEW_ACCOUNT'
    if re.search('(enter|type)\\s+destination', t, re.IGNORECASE):
        return 'ENTER_DESTINATION'
    if re.search('destination\\s+(value\\s+)?that\\s+is\\s+NOT', t, re.IGNORECASE):
        return 'ENTER_DESTINATION'
    if re.search('enter\\s+(and\\s+select\\s+)?a\\s+location', t, re.IGNORECASE):
        return 'ENTER_LOCATION'
    if website == 'autodrive' and re.search('location\\s+equals\\s+[\'\\"]', t, re.IGNORECASE):
        return 'ENTER_LOCATION'
    if re.search('search\\s+ride\\s+(details\\s+)?where\\s+the\\s+location', t, re.IGNORECASE):
        return 'SEARCH_RIDE'
    if re.search('(search|search\\s+for)\\s+.*location\\s+.*destination', t, re.IGNORECASE):
        return 'SEARCH_LOCATION'
    if re.search('search\\s+location\\s+(details|to\\s+find|for)', t, re.IGNORECASE):
        return 'SEARCH_LOCATION'
    if re.search('destination\\s+equals\\s+', t, re.IGNORECASE):
        return 'SEARCH_LOCATION'
    if re.search('(reserve|book)\\s+.*ride', t, re.IGNORECASE):
        return 'RESERVE_RIDE'
    if re.search('cancel\\s+reservation', t, re.IGNORECASE):
        return 'CANCEL_RESERVATION'
    if re.search('select\\s+(a\\s+)?date\\s+for\\s+(the\\s+|your\\s+)?trip', t, re.IGNORECASE):
        return 'SELECT_DATE'
    if re.search('select\\s+(a\\s+)?time\\s+for\\s+(my\\s+|your\\s+)?trip', t, re.IGNORECASE):
        return 'SELECT_TIME'
    if re.search('select\\s+time\\s+for\\s+my\\s+trip', t, re.IGNORECASE):
        return 'SELECT_TIME'
    if re.search('next\\s+pickup', t, re.IGNORECASE):
        return 'NEXT_PICKUP'
    if re.search('(view|navigate\\s+to)\\s+(the\\s+)?templates', t, re.IGNORECASE):
        return 'VIEW_TEMPLATES'
    if re.search('edit\\s+the\\s+template\\s+body', t, re.IGNORECASE):
        return 'TEMPLATE_BODY_EDITED'
    if re.search('cancel\\s+(the\\s+)?template', t, re.IGNORECASE):
        return 'TEMPLATE_CANCELED'
    if re.search('save\\s+(the\\s+)?email\\s+as\\s+(a\\s+)?draft', t, re.IGNORECASE):
        return 'EMAIL_SAVE_AS_DRAFT'
    if re.search('reply\\s+to\\s+the\\s+email', t, re.IGNORECASE):
        return 'REPLY_EMAIL'
    if re.search('mark\\s+as\\s+spam', t, re.IGNORECASE):
        return 'MARK_AS_SPAM'
    if re.search('(mark|move)\\s+.*(spam|junk)', t, re.IGNORECASE):
        return 'MARK_AS_SPAM'
    if re.search('star\\s+the\\s+email', t, re.IGNORECASE):
        return 'STAR_AN_EMAIL'
    if re.search('archive\\s+the\\s+email', t, re.IGNORECASE):
        return 'ARCHIVE_EMAIL'
    if re.search('delete\\s+the\\s+email', t, re.IGNORECASE):
        return 'DELETE_EMAIL'
    if re.search('forward\\s+the\\s+email', t, re.IGNORECASE):
        return 'FORWARD_EMAIL'
    if re.search('mark.*email.*important|mark.*important.*email', t, re.IGNORECASE):
        return 'MARK_EMAIL_AS_IMPORTANT'
    if re.search('mark\\s+(the\\s+)?email\\s+as\\s+unread', t, re.IGNORECASE):
        return 'MARK_AS_UNREAD'
    if re.search('view\\s+the\\s+email\\s+where', t, re.IGNORECASE):
        return 'VIEW_EMAIL'
    if re.search('change\\s+the\\s+application\\s+theme', t, re.IGNORECASE):
        return 'THEME_CHANGED'
    if re.search('edit.*draft.*email', t, re.IGNORECASE):
        return 'EDIT_DRAFT_EMAIL'
    if re.search('(next|go\\s+to\\s+the\\s+next)\\s+page\\s+of\\s+emails', t, re.IGNORECASE):
        return 'EMAILS_NEXT_PAGE'
    if re.search('(previous|go\\s+back\\s+to\\s+the\\s+previous)\\s+page\\s+of\\s+emails', t, re.IGNORECASE):
        return 'EMAILS_PREV_PAGE'
    if re.search('(clear|deselect)\\s+all\\s+selected\\s+emails', t, re.IGNORECASE):
        return 'CLEAR_SELECTION'
    if re.search('send\\s+.*using\\s+the\\s+template', t, re.IGNORECASE):
        return 'TEMPLATE_SENT'
    if re.search('send\\s+an\\s+email\\s+using\\s+the\\s+template', t, re.IGNORECASE):
        return 'TEMPLATE_SENT'
    if re.search('save.*template.*draft', t, re.IGNORECASE):
        return 'TEMPLATE_SAVED_DRAFT'
    if re.search('select\\s+the\\s+template', t, re.IGNORECASE):
        return 'TEMPLATE_SELECTED'
    if re.search('add\\s+(a\\s+)?\\d+.?minute\\s+reminder|add\\s+a\\s+reminder\\s+.*event|set\\s+a\\s+reminder', t, re.IGNORECASE):
        return 'EVENT_ADD_REMINDER'
    if re.search('remove\\s+(the\\s+)?\\d+.?minute\\s+reminder|remove\\s+(a\\s+)?reminder\\s+from|delete\\s+the\\s+reminder', t, re.IGNORECASE):
        return 'EVENT_REMOVE_REMINDER'
    if re.search('switch\\s+to\\s+week\\s+view', t, re.IGNORECASE):
        return 'SELECT_WEEK'
    if re.search('switch\\s+to\\s+month\\s+view', t, re.IGNORECASE):
        return 'SELECT_MONTH'
    if re.search('switch\\s+to\\s+day\\s+view', t, re.IGNORECASE):
        return 'SELECT_DAY'
    if re.search('switch\\s+to\\s+5.?day\\s+view', t, re.IGNORECASE):
        return 'SELECT_FIVE_DAYS'
    if re.search('(add\\s+|click.*)\\s*add\\s+calendar\\s+button', t, re.IGNORECASE):
        return 'ADD_NEW_CALENDAR'
    if re.search('create\\s+a\\s+new\\s+calendar', t, re.IGNORECASE):
        return 'CREATE_CALENDAR'
    if re.search('add\\s+an?\\s+attendee\\s+to\\s+the\\s+event', t, re.IGNORECASE):
        return 'EVENT_ADD_ATTENDEE'
    if re.search('remove\\s+an?\\s+attendee\\s+from\\s+the\\s+event', t, re.IGNORECASE):
        return 'EVENT_REMOVE_ATTENDEE'
    if re.search('delete\\s+an?\\s+added\\s+event', t, re.IGNORECASE):
        return 'DELETE_ADDED_EVENT'
    if re.search('cancel\\s+an?\\s+event', t, re.IGNORECASE):
        return 'CANCEL_ADD_EVENT'
    if re.search('open\\s+the\\s+event\\s+creation\\s+wizard', t, re.IGNORECASE):
        return 'EVENT_WIZARD_OPEN'
    if re.search('click\\s+on\\s+cell\\s+for\\s+a\\s+date', t, re.IGNORECASE):
        return 'CELL_CLICKED'
    if re.search('click.*cell.*in\\s+the\\s+5\\s+days\\s+view', t, re.IGNORECASE):
        return 'CELL_CLICKED'
    if re.search('add\\s+a\\s+new\\s+calendar\\s+event', t, re.IGNORECASE):
        return 'NEW_CALENDAR_EVENT_ADDED'
    if re.search('add\\s+an?\\s+event\\b', t, re.IGNORECASE):
        return 'ADD_EVENT'
    if re.search('(show|view)\\s+.*pending\\s+events', t, re.IGNORECASE):
        return 'VIEW_PENDING_EVENTS'
    if re.search('show\\s+me\\s+results\\s+for\\s+a\\s+search\\s+query', t, re.IGNORECASE):
        return 'SEARCH_SUBMIT'
    if re.search('add\\s+members?\\s+to\\s+the\\s+team', t, re.IGNORECASE):
        return 'AUTOLIST_TEAM_MEMBERS_ADDED'
    if re.search('assign\\s+a\\s+role\\s+.*team\\s+member', t, re.IGNORECASE):
        return 'AUTOLIST_TEAM_ROLE_ASSIGNED'
    if re.search('edit\\s+task\\s+modal\\s+open', t, re.IGNORECASE):
        return 'AUTOLIST_EDIT_TASK_MODAL_OPENED'
    if re.search('button\\s+to\\s+add\\s+a\\s+task\\s+is\\s+clicked', t, re.IGNORECASE):
        return 'AUTOLIST_ADD_TASK_CLICKED'
    if re.search('change\\s+the\\s+priority\\s+to', t, re.IGNORECASE):
        return 'AUTOLIST_SELECT_TASK_PRIORITY'
    if re.search('cancel\\s+creating\\s+the\\s+task', t, re.IGNORECASE):
        return 'AUTOLIST_CANCEL_TASK_CREATION'
    if re.search('create\\s+a\\s+team\\s+whose', t, re.IGNORECASE):
        return 'AUTOLIST_TEAM_CREATED'
    if re.search('delete\\s+task\\s+whose', t, re.IGNORECASE):
        return 'AUTOLIST_DELETE_TASK'
    if re.search('add\\s+a\\s+task\\s+whose', t, re.IGNORECASE):
        return 'AUTOLIST_TASK_ADDED'
    if re.search('add\\s+a\\s+task\\s+where', t, re.IGNORECASE):
        return 'AUTOLIST_TASK_ADDED'
    if re.search('book\\s+an?\\s+appointment\\s+where', t, re.IGNORECASE):
        return 'APPOINTMENT_BOOKED_SUCCESSFULLY'
    if re.search('search\\s+(for\\s+)?prescriptions?\\s+where', t, re.IGNORECASE):
        return 'SEARCH_PRESCRIPTION'
    if re.search('(show|retrieve)\\s+details\\s+(for\\s+a\\s+doctor|of\\s+the\\s+doctor\\s+education|of\\s+a\\s+doctor)', t, re.IGNORECASE):
        if re.search('education|certif', t, re.IGNORECASE):
            return 'VIEW_DOCTOR_EDUCATION'
        if re.search('availab', t, re.IGNORECASE):
            return 'VIEW_DOCTOR_AVAILABILITY'
        return 'VIEW_DOCTOR_PROFILE'
    if re.search('show\\s+details\\s+for\\s+a\\s+doctor', t, re.IGNORECASE):
        return 'VIEW_DOCTOR_PROFILE'
    if re.search('retrieve\\s+details\\s+of\\s+the\\s+doctor\\s+education', t, re.IGNORECASE):
        return 'VIEW_DOCTOR_EDUCATION'
    if re.search('show\\s+me\\s+the\\s+availability\\s+details\\s+for\\s+a\\s+doctor', t, re.IGNORECASE):
        return 'VIEW_DOCTOR_AVAILABILITY'
    if re.search('show\\s+me\\s+(details\\s+about\\s+)?doctors', t, re.IGNORECASE):
        return 'SEARCH_DOCTORS'
    if re.search('(search|retrieve)\\s+(medical|details\\s+of\\s+medical)', t, re.IGNORECASE):
        return 'SEARCH_MEDICAL_ANALYSIS'
    if re.search('view\\s+medical\\s+analysis', t, re.IGNORECASE):
        return 'VIEW_MEDICAL_ANALYSIS'
    if re.search('open\\s+appointment\\s+form', t, re.IGNORECASE):
        return 'OPEN_APPOINTMENT_FORM'
    if re.search('open\\s+contact\\s+doctor\\s+form', t, re.IGNORECASE):
        return 'OPEN_CONTACT_DOCTOR_FORM'
    if re.search('contact\\s+a\\s+doctor\\s+where', t, re.IGNORECASE):
        return 'DOCTOR_CONTACTED_SUCCESSFULLY'
    if re.search('contact\\s+(a\\s+)?doctor', t, re.IGNORECASE):
        return 'CONTACT_DOCTOR'
    if re.search('retrieve\\s+details\\s+of\\s+appointments', t, re.IGNORECASE):
        return 'SEARCH_APPOINTMENT'
    if re.search('request\\s+a\\s+quick\\s+appointment', t, re.IGNORECASE):
        return 'REQUEST_QUICK_APPOINTMENT'
    if re.search('doctor.*education|education.*doctor', t, re.IGNORECASE):
        return 'VIEW_DOCTOR_EDUCATION'
    if re.search('comment\\s+on\\s+the\\s+post', t, re.IGNORECASE):
        return 'COMMENT_ON_POST'
    if re.search('save\\s+the\\s+post\\s+where', t, re.IGNORECASE):
        return 'SAVE_POST'
    if re.search('follow\\s+the\\s+company\\s+page', t, re.IGNORECASE):
        return 'FOLLOW_PAGE'
    if re.search('unfollow\\s+the\\s+company\\s+page', t, re.IGNORECASE):
        return 'UNFOLLOW_PAGE'
    if re.search('(withdraw|cancel)\\s+application', t, re.IGNORECASE):
        return 'CANCEL_APPLICATION'
    if re.search('(search\\s+for|show\\s+me)\\s+users', t, re.IGNORECASE):
        return 'SEARCH_USERS'
    if re.search('go\\s+back\\s+to\\s+all\\s+jobs', t, re.IGNORECASE):
        return 'BACK_TO_ALL_JOBS'
    if re.search("navigate\\s+to\\s+the\\s+'?home'?\\s+tab", t, re.IGNORECASE):
        return 'HOME_NAVBAR'
    if re.search('show\\s+me\\s+my\\s+hidden\\s+posts', t, re.IGNORECASE):
        return 'VIEW_HIDDEN_POSTS'
    if re.search('search\\s+for\\s+jobs\\s+where\\s+the\\s+query', t, re.IGNORECASE):
        return 'SEARCH_JOBS'
    if re.search('apply\\s+for\\s+(a\\s+)?job', t, re.IGNORECASE):
        return 'APPLY_FOR_JOB'
    if re.search('edit\\s+profile\\s+to\\s+set\\s+the\\s+bio', t, re.IGNORECASE):
        return 'EDIT_PROFILE_BIO'
    if re.search('like\\s+the\\s+post', t, re.IGNORECASE):
        return 'LIKE_POST'
    if re.search('unhide\\s+the\\s+post', t, re.IGNORECASE):
        return 'UNHIDE_POST'
    if re.search('hide\\s+the\\s+post', t, re.IGNORECASE):
        return 'HIDE_POST'
    if re.search('view\\s+(the\\s+)?profile\\s+of\\s+user', t, re.IGNORECASE):
        return 'VIEW_USER_PROFILE'
    if re.search('connect\\s+with\\s+', t, re.IGNORECASE):
        return 'CONNECT_WITH_USER'
    if re.search('view\\s+the\\s+job\\s+where', t, re.IGNORECASE):
        return 'VIEW_JOB'
    if re.search('filter\\s+jobs', t, re.IGNORECASE):
        return 'FILTER_JOBS'
    if re.search('(open\\s+my\\s+saved\\s+posts|view\\s+.*saved\\s+(items|posts))', t, re.IGNORECASE):
        return 'VIEW_SAVED_POSTS'
    if re.search('(show\\s+my\\s+applied\\s+jobs|view\\s+.*applied\\s+to)', t, re.IGNORECASE):
        return 'VIEW_APPLIED_JOBS'
    if re.search('edit\\s+experience', t, re.IGNORECASE):
        return 'EDIT_EXPERIENCE'
    if re.search('add\\s+(new\\s+)?experience', t, re.IGNORECASE):
        return 'ADD_EXPERIENCE'
    if re.search('book\\s+a\\s+consultation', t, re.IGNORECASE):
        return 'BOOK_A_CONSULTATION'
    if re.search('quick\\s+hire', t, re.IGNORECASE):
        return 'QUICK_HIRE'
    if re.search('confirm\\s+hiring\\s+of\\s+a\\s+consultation', t, re.IGNORECASE):
        return 'HIRE_CONSULTANT'
    if re.search('cancel\\s+hiring\\s+of\\s+a\\s+consultation', t, re.IGNORECASE):
        return 'CANCEL_HIRE'
    if re.search('choose\\s+.*budget\\s+type', t, re.IGNORECASE):
        return 'CHOOSE_BUDGET_TYPE'
    if re.search('choose\\s+.*timeline', t, re.IGNORECASE):
        return 'CHOOSE_PROJECT_TIMELINE'
    if re.search('set\\s+hourly\\s+rate', t, re.IGNORECASE):
        return 'SET_RATE_RANGE'
    if re.search('write\\s+a\\s+job\\s+description', t, re.IGNORECASE):
        return 'WRITE_JOB_DESCRIPTION'
    if re.search('send\\s+a\\s+message\\s+to\\s+an?\\s+expert', t, re.IGNORECASE):
        return 'CONTACT_EXPERT_MSG_SENT'
    if re.search('contact\\s+an?\\s+expert\\s+where', t, re.IGNORECASE):
        return 'CONTACT_EXPERT_OPENED'
    if re.search('edit\\s+profile\\s+name', t, re.IGNORECASE):
        return 'EDIT_PROFILE_NAME'
    if re.search('browse\\s+.*favorite\\s+expert', t, re.IGNORECASE):
        return 'BROWSE_FAVORITE_EXPERT'
    if re.search('select\\s+favorite\\s+expert', t, re.IGNORECASE):
        return 'FAVORITE_EXPERT_SELECTED'
    if re.search('remove\\s+favorite\\s+expert', t, re.IGNORECASE):
        return 'FAVORITE_EXPERT_REMOVED'
    if re.search('(clicks?\\s+favorites?\\s+to\\s+view|open\\s+the\\s+favorites?\\s+section|navbar.*favorites?|favorites?.*navbar)', t, re.IGNORECASE):
        return 'NAVBAR_FAVORITES_CLICK'
    if re.search('(clicks?\\s+hire\\s+later\\s+to\\s+view|open\\s+the\\s+hire\\s+later\\s+section|navbar.*hire.?later|hire.?later.*navbar)', t, re.IGNORECASE):
        return 'NAVBAR_HIRE_LATER_CLICK'
    if re.search('decide\\s+to\\s+remove\\s+expert\\s+from\\s+hire\\s+later', t, re.IGNORECASE):
        return 'HIRE_LATER_REMOVED'
    if re.search('decide\\s+to\\s+hire\\s+later', t, re.IGNORECASE):
        return 'HIRE_LATER'
    if re.search('hire\\s+(a\\s+)?(consultant|expert|later)', t, re.IGNORECASE):
        if 'later' in t:
            return 'HIRE_LATER'
        return 'HIRE_BTN_CLICKED'
    if re.search('show\\s+me\\s+details\\s+about\\s+a\\s+hiring\\s+team', t, re.IGNORECASE):
        return 'SELECT_HIRING_TEAM'
    if re.search('select\\s+a\\s+project\\s+size', t, re.IGNORECASE):
        return 'CHOOSE_PROJECT_SIZE'
    if re.search('closing\\s+the\\s+job\\s+posting\\s+window', t, re.IGNORECASE):
        return 'CLOSE_POST_A_JOB_WINDOW'
    if re.search('clicks?\\s+on\\s+the\\s+jobs?\\s+option\\s+in\\s+the\\s+navbar', t, re.IGNORECASE):
        return 'NAVBAR_JOBS_CLICK'
    if re.search('clicks?\\s+on\\s+.?hires?.?\\s+from\\s+the\\s+navbar', t, re.IGNORECASE):
        return 'NAVBAR_HIRES_CLICK'
    if re.search('searches?\\s+for\\s+a\\s+skill', t, re.IGNORECASE):
        return 'SEARCH_SKILL'
    if re.search('(job\\s+posting|writing\\s+(a\\s+)?(strong\\s+)?title\\s+of\\s+(the\\s+)?job)', t, re.IGNORECASE):
        return 'WRITE_JOB_TITLE'
    if re.search('edit\\s+profile\\s+about', t, re.IGNORECASE):
        return 'EDIT_ABOUT'
    if re.search('update\\s+my\\s+profile\\s+about\\s+section', t, re.IGNORECASE):
        return 'EDIT_ABOUT'
    if re.search('edit\\s+profile\\s+(location|email)', t, re.IGNORECASE):
        if 'location' in t:
            return 'EDIT_PROFILE_LOCATION'
        return 'EDIT_PROFILE_EMAIL'
    if re.search('edit\\s+profile\\s+email', t, re.IGNORECASE):
        return 'EDIT_PROFILE_EMAIL'
    if re.search('(view|show)\\s+the\\s+hotel\\s+where', t, re.IGNORECASE):
        return 'VIEW_HOTEL'
    if re.search('go\\s+back\\s+to\\s+(the\\s+)?(all\\s+)?hotels|return\\s+to\\s+.*hotel\\s+(dashboard|listing)', t, re.IGNORECASE):
        return 'BACK_TO_ALL_HOTELS'
    if re.search('book\\s+.*from\\s+(my\\s+)?wishlist|book\\s+.*saved\\s+in\\s+wishlist', t, re.IGNORECASE):
        return 'BOOK_FROM_WISHLIST'
    if re.search('confirm\\s+the\\s+booking', t, re.IGNORECASE):
        return 'BOOKING_CONFIRM'
    if re.search('(adjust|set|change)\\s+the\\s+number\\s+of\\s+guests', t, re.IGNORECASE):
        return 'EDIT_NUMBER_OF_GUESTS'
    if re.search('select\\s+people\\s+(equals|not|greater|less)', t, re.IGNORECASE):
        return 'PEOPLE_SELECTED'
    if re.search('(open\\s+)?guest\\s+selector\\s+dropdown', t, re.IGNORECASE):
        return 'PEOPLE_DROPDOWN_OPENED'
    if re.search('select\\s+(a\\s+)?payment\\s+method', t, re.IGNORECASE):
        return 'PAYMENT_METHOD_SELECTED'
    if re.search('(reserve|book)\\s+the\\s+hotel', t, re.IGNORECASE):
        return 'RESERVE_HOTEL'
    if re.search('share\\s+the\\s+hotel\\s+listing', t, re.IGNORECASE):
        return 'SHARE_HOTEL'
    if re.search('show\\s+(me\\s+)?details\\s+for\\s+popular\\s+hotels', t, re.IGNORECASE):
        return 'POPULAR_HOTELS_VIEWED'
    if re.search('search\\s+for\\s+hotels?', t, re.IGNORECASE):
        return 'SEARCH_HOTEL'
    if re.search('submit\\s+a\\s+review\\b(?!.*restaurant)', t, re.IGNORECASE):
        return 'SUBMIT_REVIEW'
    if re.search('add\\s+to\\s+wishlist.*hotel', t, re.IGNORECASE):
        return 'ADD_TO_WISHLIST_HOTEL'
    if re.search('apply.*filter.*hotel|show\\s+details\\s+for\\s+hotels', t, re.IGNORECASE):
        return 'APPLY_FILTERS'
    if re.search('(empty|clear)\\s+(my\\s+)?cart|remove\\s+all\\s+items\\s+from\\s+(my\\s+)?cart', t, re.IGNORECASE):
        return 'EMPTY_CART'
    if re.search('place\\s+(the\\s+)?order', t, re.IGNORECASE):
        return 'PLACE_ORDER'
    if re.search('(next|show\\s+me\\s+the\\s+next)\\s+set\\s+of\\s+restaurants', t, re.IGNORECASE):
        return 'RESTAURANT_NEXT_PAGE'
    if re.search('go\\s+back\\s+to\\s+the\\s+previous\\s+page\\s+of\\s+restaurants', t, re.IGNORECASE):
        return 'RESTAURANT_PREV_PAGE'
    if re.search('return\\s+to\\s+all\\s+restaurants', t, re.IGNORECASE):
        return 'BACK_TO_ALL_RESTAURANTS'
    if re.search('increase\\s+the\\s+quantity\\s+of\\s+the\\s+item\\s+in\\s+the\\s+cart', t, re.IGNORECASE):
        return 'ITEM_INCREMENTED'
    if re.search('search\\s+for\\s+restaurants?\\s+(where|that)', t, re.IGNORECASE):
        return 'SEARCH_DELIVERY_RESTAURANT'
    if re.search('submit\\s+a\\s+review\\s+for\\s+restaurant', t, re.IGNORECASE):
        return 'REVIEW_CREATED'
    if re.search('submit\\s+(a\\s+)?review\\s+for\\s+(a\\s+)?restaurant', t, re.IGNORECASE):
        return 'REVIEW_SUBMITTED'
    if re.search('add\\s+an?\\s+address\\s+that\\s+is', t, re.IGNORECASE):
        return 'ADDRESS_ADDED'
    if re.search('set\\s+dropoff\\s+preference', t, re.IGNORECASE):
        return 'DROPOFF_PREFERENCE'
    if re.search('select\\s+(a\\s+)?delivery\\s+priority', t, re.IGNORECASE):
        return 'DELIVERY_PRIORITY_SELECTED'
    if re.search('view\\s+the\\s+details\\s+of\\s+a\\s+restaurant\\s+where', t, re.IGNORECASE):
        return 'VIEW_DELIVERY_RESTAURANT'
    if re.search('show\\s+all\\s+restaurants', t, re.IGNORECASE):
        return 'VIEW_ALL_RESTAURANTS'
    if re.search('(go\\s+to\\s+)?checkout\\s+and\\s+show\\s+the\\s+order', t, re.IGNORECASE):
        return 'OPEN_CHECKOUT_PAGE'
    if re.search('(show|view|display)\\s+.*full\\s+menu', t, re.IGNORECASE):
        return 'VIEW_FULL_MENU'
    if re.search('(select|remove)\\s+the\\s+tag\\s+filter', t, re.IGNORECASE):
        return 'TAG_FILTER_SELECTED'
    if re.search('(reservation\\s+is\\s+for\\s+a\\s+|occasion\\s+type|as\\s+the\\s+occasion)', t, re.IGNORECASE):
        return 'OCCASION_SELECTED'
    if re.search('select\\s+(the\\s+)?date\\s+[\'\\"]', t, re.IGNORECASE):
        return 'DATE_SELECTED'
    if re.search('select\\s+(the\\s+)?time\\s+(equals|not)', t, re.IGNORECASE):
        return 'TIME_SELECTED'
    if re.search('edit\\s+your\\s+review', t, re.IGNORECASE):
        return 'REVIEW_EDITED'
    if re.search('delete\\s+your\\s+review', t, re.IGNORECASE):
        return 'REVIEW_DELETED'
    if re.search('book\\s+a\\s+table', t, re.IGNORECASE):
        return 'BOOK_RESTAURANT'
    if re.search('(complete|finalize|finish)\\s+.*reservation', t, re.IGNORECASE):
        return 'RESERVATION_COMPLETE'
    if re.search('open\\s+the\\s+contact\\s+page', t, re.IGNORECASE):
        return 'CONTACT_PAGE_VIEW'
    if re.search('search\\s+for\\s+restaurants?\\s+where\\s+the\\s+query', t, re.IGNORECASE):
        return 'SEARCH_RESTAURANT'
    if re.search('(please\\s+)?collapse\\s+the\\s+(expanded\\s+)?menu(\\s+view)?', t, re.IGNORECASE):
        return 'COLLAPSE_MENU'
    if re.search('click\\s+the\\s+contact\\s+card\\s+where', t, re.IGNORECASE):
        return 'CONTACT_CARD_CLICK'
    if re.search('scroll\\s+in\\s+the\\s+direction', t, re.IGNORECASE):
        return 'SCROLL_VIEW'
    if re.search('show\\s+details\\s+for\\s+the\\s+help\\s+category', t, re.IGNORECASE):
        return 'HELP_CATEGORY_SELECTED'
    if re.search('(navigate\\s+to|find)\\s+the\\s+help\\s+page', t, re.IGNORECASE):
        return 'HELP_PAGE_VIEW'
    if re.search('(open|show).*guest.*selector.*dropdown.*number\\s+of\\s+people', t, re.IGNORECASE):
        return 'PEOPLE_DROPDOWN_OPENED'
    if re.search('select.*country.*dropdown|please\\s+select\\s+the\\s+country', t, re.IGNORECASE):
        return 'COUNTRY_SELECTED'
    if re.search('expand\\s+the\\s+faq\\s+item', t, re.IGNORECASE):
        return 'HELP_FAQ_TOGGLED'
    if re.search('open\\s+the\\s+help', t, re.IGNORECASE):
        return 'HELP_VIEWED'
    if re.search('click\\s+on\\s+the\\s+feature.*on\\s+the\\s+about\\s+page', t, re.IGNORECASE):
        return 'ABOUT_FEATURE_CLICK'
    if re.search('contact\\s+support\\s+regarding', t, re.IGNORECASE):
        return 'CONTACT_FORM_SUBMIT'
    if re.search('view\\s+the\\s+details\\s+of\\s+a\\s+restaurant', t, re.IGNORECASE):
        return 'VIEW_RESTAURANT'
    if re.search('show\\s+details\\s+for\\s+(a|the)\\s+restaurant', t, re.IGNORECASE):
        return 'VIEW_RESTAURANT'
    if re.search('search\\s+for\\s+(?!hotels?|restaurants?|doctors?|emails?|books?|movies?|films?|matters?|clients?|jobs?|users?|the\\s+book)\\w+', t, re.IGNORECASE):
        return 'SEARCH_PRODUCT'
    if re.search('(expand|collapse)\\s+(the\\s+)?.*section|explore\\s+further', t, re.IGNORECASE):
        return 'DETAILS_TOGGLE'
    if re.search('update\\s+quantity\\s+of\\s+item\\s+with\\s+title', t, re.IGNORECASE):
        return 'QUANTITY_CHANGED'
    if re.search('update\\s+the\\s+quantity\\s+of\\s+the\\s+item\\s+in\\s+my\\s+cart', t, re.IGNORECASE):
        return 'QUANTITY_CHANGED'
    if re.search('update\\s+quantity\\s+of\\s+item', t, re.IGNORECASE):
        return 'QUANTITY_CHANGED'
    if re.search('increase\\s+the\\s+quantity', t, re.IGNORECASE):
        return 'ITEM_INCREMENTED'
    if re.search('show\\s+details\\s+for\\s+a\\s+product', t, re.IGNORECASE):
        return 'VIEW_DETAIL'
    if re.search('filter\\s+to\\s+show\\s+only\\s+products\\s+in\\s+the\\s+category', t, re.IGNORECASE):
        return 'CATEGORY_FILTER'
    if re.search('(show\\s+me\\s+my\\s+saved\\s+items|my\\s+wishlist|show.*wishlist)', t, re.IGNORECASE):
        return 'VIEW_WISHLIST'
    if re.search('proceed\\s+to\\s+checkout', t, re.IGNORECASE):
        return 'PROCEED_TO_CHECKOUT'
    if re.search('(complete\\s+my\\s+purchase|complete\\s+my\\s+order)', t, re.IGNORECASE):
        return 'ORDER_COMPLETED'
    if re.search('scroll\\s+(left|right)\\s+in\\s+the\\s+carousel', t, re.IGNORECASE):
        return 'CAROUSEL_SCROLL'
    if re.search('share\\s+the\\s+link\\s+to\\s+a\\s+product', t, re.IGNORECASE):
        return 'SHARE_PRODUCT'
    if re.search('add.*this.*item.*to.*cart', t, re.IGNORECASE):
        return 'ADD_TO_CART'
    if re.search('(add|put).*wishlist\\s+(a\\s+)?(?:hotel|item|product|book)', t, re.IGNORECASE):
        return 'ADD_TO_WISHLIST'
    if re.search('(show|view)\\s+my\\s+shopping\\s+cart', t, re.IGNORECASE):
        return 'VIEW_CART'
    if re.search('search\\s+for\\s+clients?\\s+where\\s+the\\s+query', t, re.IGNORECASE):
        return 'SEARCH_CLIENT'
    if re.search('add\\s+(a\\s+)?new\\s+log\\s+(entry\\s+)?where', t, re.IGNORECASE):
        return 'NEW_LOG_ADDED'
    if re.search('delete\\s+the\\s+log\\s+(entry\\s+)?where', t, re.IGNORECASE):
        return 'LOG_DELETE'
    if re.search('delete\\s+the\\s+client\\s+where', t, re.IGNORECASE):
        return 'DELETE_CLIENT'
    if re.search('update\\s+the\\s+matter\\s+where', t, re.IGNORECASE):
        return 'UPDATE_MATTER'
    if re.search('add\\s+a\\s+new\\s+client', t, re.IGNORECASE):
        return 'ADD_CLIENT'
    if re.search('add\\s+a\\s+new\\s+matter', t, re.IGNORECASE):
        return 'ADD_NEW_MATTER'
    if re.search('search\\s+for\\s+matters?\\s+where\\s+the\\s+query', t, re.IGNORECASE):
        return 'SEARCH_MATTER'
    if re.search('show\\s+me\\s+details\\s+for\\s+clients?\\s+whose', t, re.IGNORECASE):
        return 'FILTER_CLIENTS'
    if re.search('show\\s+me\\s+matters?\\s+where\\s+the\\s+status', t, re.IGNORECASE):
        return 'FILTER_MATTER_STATUS'
    if re.search('show\\s+me\\s+details\\s+about\\s+a\\s+document', t, re.IGNORECASE):
        return 'DOCUMENT_DELETED'
    if re.search('sort\\s+matters?\\s+so\\s+that', t, re.IGNORECASE):
        return 'SORT_MATTER_BY_CREATED_AT'
    if re.search('change\\s+(user\\s+)?name\\s+to', t, re.IGNORECASE):
        return 'CHANGE_USER_NAME'
    if re.search('show.*pending\\s+events\\s+on\\s+the\\s+calendar', t, re.IGNORECASE):
        return 'VIEW_PENDING_EVENTS'
    if re.search('add\\s+a\\s+new\\s+calendar\\s+event\\s+where', t, re.IGNORECASE):
        return 'NEW_CALENDAR_EVENT_ADDED'
    if re.search('(delete|remove)\\s+(your\\s+)?(user[- _]?registered\\s+)?book', t, re.IGNORECASE):
        if re.search('\\b(login|sign.?in)\\b', t, re.IGNORECASE):
            return 'DELETE_BOOK'
    if re.search('modify\\s+your\\s+book|edit\\s+(your\\s+)?book\\s+where', t, re.IGNORECASE):
        return 'EDIT_BOOK'
    if re.search('remove\\s+from\\s+the\\s+reading\\s+list', t, re.IGNORECASE):
        return 'REMOVE_FROM_READING_LIST'
    if re.search('go\\s+to\\s+the\\s+contact\\s+page\\s+and\\s+send', t, re.IGNORECASE):
        return 'CONTACT_BOOK'
    if re.search('register\\s+with\\s+the\\s+following\\s+username', t, re.IGNORECASE):
        return 'REGISTRATION_BOOK'
    if re.search('show\\s+details\\s+for\\s+a\\s+book\\s+where', t, re.IGNORECASE):
        return 'BOOK_DETAIL'
    if re.search('filter\\s+books?\\s+where', t, re.IGNORECASE):
        return 'FILTER_BOOK'
    if re.search('search\\s+for\\s+(the\\s+)?book\\s+with\\s+the\\s+query', t, re.IGNORECASE):
        return 'SEARCH_BOOK'
    if re.search('view\\s+the\\s+shopping\\s+cart.*all\\s+items|see\\s+all\\s+items.*cart', t, re.IGNORECASE):
        return 'VIEW_CART_BOOK'
    if re.search('login\\s+for\\s+the\\s+following\\s+username', t, re.IGNORECASE):
        return 'LOGIN_BOOK'
    if re.search('authenticate\\s+with\\s+username.*view\\s+the\\s+shopping\\s+cart', t, re.IGNORECASE):
        return 'VIEW_CART_BOOK'
    if re.search('(add|create)\\s+a\\s+book\\s+(with|where)\\s+genres?', t, re.IGNORECASE):
        return 'ADD_BOOK'
    if re.search('leave\\s+a\\s+comment\\s+on\\s+a\\s+book', t, re.IGNORECASE):
        return 'ADD_COMMENT_BOOK'
    if re.search('open\\s+preview\\s+of\\s+a\\s+book', t, re.IGNORECASE):
        return 'OPEN_PREVIEW'
    if re.search('add\\s+(to\\s+)?watchlist', t, re.IGNORECASE):
        return 'ADD_TO_WATCHLIST'
    if re.search('remove\\s+from\\s+watchlist', t, re.IGNORECASE):
        return 'REMOVE_FROM_WATCHLIST'
    if re.search('share\\s+movie\\s+details', t, re.IGNORECASE):
        return 'SHARE_MOVIE'
    if re.search('watch\\s+the\\s+trailer\\s+for\\s+a\\s+movie', t, re.IGNORECASE):
        return 'WATCH_TRAILER'
    if re.search('(navigate\\s+to\\s+(a\\s+)?movie\\s+page|show\\s+details?\\s+for\\s+(a\\s+)?movie)\\s+where', t, re.IGNORECASE):
        return 'FILM_DETAIL'
    if re.search('search\\s+for\\s+(a\\s+)?movie\\s+where\\s+the\\s+query', t, re.IGNORECASE):
        return 'SEARCH_FILM'
    if re.search('click\\s+on\\s+buy\\s+now\\s+to\\s+initiate\\s+checkout', t, re.IGNORECASE):
        return 'CHECKOUT_STARTED'
    if re.search('navigate\\s+to\\s+the\\s+about\\s+page', t, re.IGNORECASE):
        return 'ABOUT_PAGE_VIEW'
    if re.search('open\\s+the\\s+date\\s+selector', t, re.IGNORECASE):
        return 'DATE_DROPDOWN_OPENED'
    if re.search('(open|show\\s+details\\s+for\\s+opening)\\s+the\\s+time\\s+(selection\\s+)?dropdown', t, re.IGNORECASE):
        return 'TIME_DROPDOWN_OPENED'
    if re.search('(retrieve\\s+details\\s+of\\s+a\\s+contact\\s+form|submit.*contact.*form.*email.*contains)', t, re.IGNORECASE):
        return 'CONTACT_FORM_SUBMIT'
    if re.search('(retrieve|show)\\s+details\\s+of\\s+billing\\s+(entries|records)|billing\\s+entries\\s+where', t, re.IGNORECASE):
        return 'BILLING_SEARCH'
    if re.search('edit\\s+log\\s+entry\\s+where', t, re.IGNORECASE):
        return 'LOG_EDITED'
    if re.search('archive\\s+the\\s+matter\\s+where', t, re.IGNORECASE):
        return 'ARCHIVE_MATTER'
    if re.search('(retrieve|show)\\s+details\\s+(of|for)\\s+a?\\s*client\\s+whose', t, re.IGNORECASE):
        return 'VIEW_CLIENT_DETAILS'
    if re.search('(retrieve|show)\\s+details\\s+(of|for)\\s+(the\\s+)?matter\\s+(whose|where)', t, re.IGNORECASE):
        return 'VIEW_MATTER_DETAILS'
    if re.search('add\\s+a\\s+label\\s+to\\s+the\\s+email\\s+where', t, re.IGNORECASE):
        return 'ADD_LABEL'
    if re.search('send\\s+an\\s+email\\s+to\\s+[\'\\"]', t, re.IGNORECASE):
        return 'SEND_EMAIL'
    if re.search('search\\s+for\\s+emails?\\s+where\\s+the\\s+query', t, re.IGNORECASE):
        return 'SEARCH_EMAIL'
    if re.search('delete\\s+the\\s+review\\s+for\\s+the\\s+restaurant', t, re.IGNORECASE):
        return 'DELETE_REVIEW'
    if re.search('show\\s+me\\s+restaurants?\\s+that\\s+do\\s+NOT', t, re.IGNORECASE):
        return 'RESTAURANT_FILTER'
    if re.search('add\\s+a?\\s*menu\\s+item\\s+to\\s+(my\\s+)?cart', t, re.IGNORECASE):
        return 'ADD_TO_CART_MENU_ITEM'
    if re.search('open\\s+the\\s+add.?to.?cart\\s+modal', t, re.IGNORECASE):
        return 'ADD_TO_CART_MODAL_OPEN'
    if re.search('start\\s+a\\s+quick\\s+order', t, re.IGNORECASE):
        return 'QUICK_ORDER_STARTED'
    if re.search('open\\s+the\\s+FAQ\\s+item\\s+where', t, re.IGNORECASE):
        return 'FAQ_OPENED'
    if re.search('message\\s+the\\s+host\\s+where', t, re.IGNORECASE):
        return 'MESSAGE_HOST'
    if re.search('edit\\s+check.?in.*check.?out\\s+dates', t, re.IGNORECASE):
        return 'EDIT_CHECK_IN_OUT_DATES'
    if re.search('open\\s+my\\s+wishlist\\s+to\\s+view\\s+saved\\s+hotels', t, re.IGNORECASE):
        return 'WISHLIST_OPENED'
    if re.search('show\\s+me\\s+the\\s+wishlist\\s+so\\s+i\\s+can\\s+view', t, re.IGNORECASE):
        return 'WISHLIST_OPENED'
    if re.search('remove\\s+from\\s+my\\s+wishlist', t, re.IGNORECASE):
        return 'REMOVE_FROM_WISHLIST'
    if re.search('open\\s+the\\s+jobs?\\s+tab\\s+from\\s+the\\s+navbar', t, re.IGNORECASE):
        return 'JOBS_NAVBAR'
    if re.search('edit\\s+profile\\s+information', t, re.IGNORECASE):
        return 'EDIT_PROFILE'
    if re.search('edit\\s+profile\\s+for\\s+the\\s+user\\s+whose', t, re.IGNORECASE):
        return 'EDIT_PROFILE'
    if re.search('post\\s+a\\s+status\\s+update', t, re.IGNORECASE):
        return 'POST_STATUS'
    if re.search('remove\\s+post\\s+where', t, re.IGNORECASE):
        return 'REMOVE_POST'
    if re.search('edit\\s+profile\\s+title\\s+where', t, re.IGNORECASE):
        return 'EDIT_PROFILE_TITLE'
    if re.search("(user\\s+clicks?|click)\\s+'?post\\s+a\\s+job'?|initiate.*posting.*job|clicks?\\s+'?post\\s+a\\s+job'?\\s+button", t, re.IGNORECASE):
        return 'POST_A_JOB'
    if re.search("clicks?\\s+the\\s+'?experts?'?\\s+option\\s+in\\s+the\\s+navbar|list\\s+of\\s+all\\s+experts.*clicks?\\s+the\\s+'?experts?", t, re.IGNORECASE):
        return 'NAVBAR_EXPERTS_CLICK'
    if re.search('show\\s+the\\s+list\\s+of\\s+all\\s+experts', t, re.IGNORECASE):
        return 'NAVBAR_EXPERTS_CLICK'
    if re.search('add\\s+a\\s+skill\\s+where\\s+skill', t, re.IGNORECASE):
        return 'ADD_SKILL'
    if re.search('submit\\s+a\\s+job\\s+with\\s+title', t, re.IGNORECASE):
        return 'SUBMIT_JOB'
    if re.search('decide\\s+to\\s+start\\s+hiring', t, re.IGNORECASE):
        return 'HIRE_LATER_START'
    if re.search('select\\s+(the\\s+)?calendar\\s+(whose|where|that|named)', t, re.IGNORECASE):
        return 'SELECT_CALENDAR'
    if re.search('unselect\\s+the\\s+calendar', t, re.IGNORECASE):
        return 'UNSELECT_CALENDAR'
    if re.search("go\\s+to\\s+today'?s?\\s+date\\s+in\\s+the\\s+calendar", t, re.IGNORECASE):
        return 'SELECT_TODAY'
    if re.search('complete\\s+task\\s+where\\s+the\\s+name\\s+equals', t, re.IGNORECASE):
        return 'AUTOLIST_COMPLETE_TASK'
    if re.search('(please\\s+)?set\\s+the\\s+date\\s+for\\s+the\\s+task\\s+to', t, re.IGNORECASE):
        return 'AUTOLIST_SELECT_DATE_FOR_TASK'
    if re.search('view\\s+trip\\s+details\\s+for\\s+(a\\s+)?(trip|ride)\\s+where', t, re.IGNORECASE):
        return 'TRIP_DETAILS'
    if re.search('select\\s+car\\s+options\\s+where', t, re.IGNORECASE):
        return 'SELECT_CAR'
    if re.search('search\\s+destination\\s+where\\s+the\\s+destination', t, re.IGNORECASE):
        return 'SEARCH_DESTINATION'
    if re.search('select\\s+date\\s+for\\s+(your|my)\\s+trip\\s+as', t, re.IGNORECASE):
        return 'SELECT_DATE'
    if re.search('refill\\s+prescription\\s+where', t, re.IGNORECASE):
        return 'REFILL_PRESCRIPTION'
    if re.search('(show\\s+me\\s+details\\s+to\\s+refill|show\\s+details\\s+for\\s+a\\s+prescription)', t, re.IGNORECASE):
        return 'VIEW_PRESCRIPTION'
    if re.search('(show|retrieve|get)\\s+details\\s+(for|of)\\s+doctor\\s+reviews', t, re.IGNORECASE):
        return 'FILTER_DOCTOR_REVIEWS'
    if re.search('(login\\s+for\\s+the\\s+following|login\\s+with\\s+(a\\s+)?specific).*username.*then\\s+logout', t, re.IGNORECASE):
        return 'LOGOUT_BOOK'
    if re.search('first.*authenticate.*username.*then.*logout', t, re.IGNORECASE):
        return 'LOGOUT_BOOK'
    if re.search('\\b(logout|sign.?out|log.?out)\\b', t) and re.search('\\b(login|sign.?in|log.?in)\\b', t):
        return 'LOGIN_THEN_LOGOUT'
    if re.search('\\b(add|remove|delete).*(watchlist|reading.?list|wishlist|cart)\\b', t) and re.search('\\b(login|sign.?in)\\b', t):
        return 'LOGIN_THEN_LIST_ACTION'
    if re.search('\\b(add|post|submit).*(comment|review|rating)\\b', t) and re.search('\\b(login|sign.?in)\\b', t):
        return 'LOGIN_THEN_COMMENT'
    if re.search('\\b(add|insert|create|register).*(films?|movies?|books?)\\b', t) and re.search('\\b(login|sign.?in)\\b', t):
        return 'LOGIN_THEN_ADD_ITEM'
    if re.search('\\b(edit|update|modify).*(films?|movies?|books?)\\b', t) and re.search('\\b(login|sign.?in)\\b', t):
        return 'LOGIN_THEN_EDIT_ITEM'
    if re.search('\\b(delete|remove).*(films?|movies?|books?)\\b', t) and re.search('\\b(login|sign.?in)\\b', t):
        return 'LOGIN_THEN_DELETE_ITEM'
    if re.search('\\b(edit|update|modify).*(profile|account|user)\\b', t) and re.search('\\b(login|sign.?in)\\b', t):
        return 'LOGIN_THEN_EDIT_PROFILE'
    if re.search('\\b(purchase|buy|checkout|order)\\b', t) and re.search('\\b(login|sign.?in|authenticate)\\b', t):
        return 'LOGIN_THEN_PURCHASE'
    if re.search('reorder\\s+the\\s+recent\\s+item', t, re.IGNORECASE):
        return 'QUICK_REORDER'
    if re.search('show\\s+details\\s+for\\s+editing\\s+a\\s+cart\\s+item', t, re.IGNORECASE):
        return 'EDIT_CART_ITEM'
    if re.search('delete\\s+the\\s+matter\\s+where', t, re.IGNORECASE):
        return 'DELETE_MATTER'
    if re.search('create\\s+a\\s+new\\s+label', t, re.IGNORECASE):
        return 'CREATE_LABEL'
    if re.search('delete\\s+task\\b', t, re.IGNORECASE):
        return 'DELETE_TASK'
    if re.search('(create|add|new)\\s+task\\b', t, re.IGNORECASE):
        return 'CREATE_TASK'
    if re.search('(edit|update|modify)\\s+task\\b', t, re.IGNORECASE):
        return 'EDIT_TASK'
    if re.search('\\b(register|sign.?up|create.*account|fill.*registration)\\b', t):
        return 'REGISTRATION'
    if re.search('\\b(login|sign.?in|log.?in|fill.*login|authenticate)\\b', t):
        return 'LOGIN'
    if re.search('\\b(search|look.?for|find|look.?up)\\b', t) and re.search('\\b(films?|movies?|books?)\\b', t):
        return 'SEARCH_ITEM'
    if re.search('\\b(filter|sort)\\b', t) and re.search('\\b(films?|movies?|books?)\\b', t):
        return 'FILTER_ITEM'
    _already_on_detail = url and re.search('/(?:products?|items?|details?|films?|books?|movies?)/\\d+', url)
    if not _already_on_detail and re.search('\\b(navigate|go.?to|view.?detail|detail.?page|film.?page|book.?page|movie.?page)\\b', t):
        return 'NAVIGATE_DETAIL'
    if re.search('\\b(share)\\b', t) and re.search('\\b(films?|movies?|books?)\\b', t):
        return 'SHARE_ITEM'
    if re.search('\\b(watch.*trailer|play.*trailer|trailer)\\b', t):
        return 'WATCH_TRAILER'
    if re.search('\\b(preview|open.*preview)\\b', t):
        return 'OPEN_PREVIEW'
    if re.search('\\b(add|put).*(cart|basket)\\b', t):
        return 'ADD_TO_CART'
    if re.search('\\b(remove|delete).*(cart|basket)\\b', t):
        return 'REMOVE_FROM_CART'
    if re.search('\\b(view|show).*(cart|basket)\\b', t):
        return 'VIEW_CART'
    if re.search('\\b(purchase|buy|checkout|order)\\b', t):
        return 'PURCHASE'
    if re.search('\\b(contact|send.*message|fill.*contact)\\b', t):
        return 'CONTACT'
    if re.search('\\b(add|post|submit).*(comment|review)\\b', t):
        return 'ADD_COMMENT'
    if re.search('\\b(watchlist|reading.?list|wishlist)\\b', t):
        return 'LIST_ACTION'
    return 'GENERAL'

def try_shortcut(task_type: str | None, candidates: list[Candidate], soup: BeautifulSoup, step_index: int) -> list[dict] | None:
    if task_type is None:
        return None
    if task_type == 'login':
        if is_already_logged_in(soup):
            return None
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
    indicators = ['logout', 'log out', 'sign out']
    for tag in soup.find_all(['nav', 'header', 'a', 'button']):
        tag_text = tag.get_text(separator=' ').lower().strip()
        for indicator in indicators:
            if indicator in tag_text:
                return True
    return False