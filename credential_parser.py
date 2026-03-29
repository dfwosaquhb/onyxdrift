from __future__ import annotations
import re
from typing import Optional

def extract_credentials_from_task(task: str) -> dict[str, str]:
    creds: dict[str, str] = {}
    t = task or ''
    patterns = [('(?:user[- _]?name|user)', 'username'), ('(?:email)', 'email'), ('(?:password|pass)', 'password'), ('signup[_-]?username', 'signup_username'), ('signup[_-]?email', 'signup_email'), ('signup[_-]?password', 'signup_password'), ('cvv', 'cvv'), ('(?:zipcode|zip)', 'zipcode'), ('country', 'country'), ('priority', 'priority'), ('guests?(?:_set)?', 'guests'), ('rating', 'rating'), ('reviews?', 'reviews')]

    def _extract_field_equals(field_pat: str) -> Optional[str]:
        for pat in ['(?<!\\w)' + field_pat + "\\s+equals?\\s+'([^']*)'", '(?<!\\w)' + field_pat + '\\s+equals?\\s+"([^"]*)"', '(?<!\\w)' + field_pat + '\\s+equals?\\s+([^\\s,\'\\"\\n\\]]+)']:
            mm = re.search(pat, t, re.IGNORECASE)
            if mm:
                prefix = t[max(0, mm.start() - 5):mm.start()].lower()
                if 'not' in prefix:
                    continue
                return mm.group(1).rstrip('.,;:')
        return None
    for (field_pat, key) in patterns:
        if key not in creds:
            val = _extract_field_equals(field_pat)
            if val is not None:
                creds[key] = val
    m = re.search("writing\\s+a\\s+(?:strong\\s+)?title\\s+of\\s+(?:the\\s+)?job\\s+for\\s+'([^']+)'", t, re.IGNORECASE)
    if not m:
        m = re.search("title\\s+of\\s+(?:the\\s+)?job\\s+for\\s+'([^']+)'", t, re.IGNORECASE)
    if m:
        creds['job_title'] = m.group(1)
    m2 = re.search("job\\s+posting.*?query\\s+CONTAINS\\s+'([^']+)'", t, re.IGNORECASE)
    if not m2:
        m2 = re.search("writing.*?title.*?(?:query\\s+)?CONTAINS\\s+'([^']+)'", t, re.IGNORECASE)
    if m2 and 'job_title' not in creds:
        creds['job_title_contains'] = m2.group(1)
    for (field_label, key) in [('username', 'username'), ('email', 'email'), ('password', 'password')]:
        if key not in creds:
            m3 = re.search('\\b' + field_label + "\\s*:\\s*'([^']*)'", t, re.IGNORECASE)
            if m3:
                creds[key] = m3.group(1)
    for (placeholder, key, default) in [('<username>', 'username', 'user'), ('<password>', 'password', 'Passw0rd!'), ('<web_agent_id>', 'web_agent_id', '1')]:
        if placeholder in t:
            if key not in creds or creds.get(key, '').startswith('<'):
                creds[key] = default
    for key in ('username', 'email', 'signup_username', 'signup_email'):
        if key in creds and '<web_agent_id>' in creds[key]:
            creds[key] = creds[key].replace('<web_agent_id>', '1')
    return creds