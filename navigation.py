from __future__ import annotations
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode, parse_qsl
_LOCALHOST_HOSTS = {'localhost', '127.0.0.1', '::1'}
_ALLOWED_SCHEMES = {'http', 'https'}

def extract_seed(url: str) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    seed_vals = params.get('seed')
    if seed_vals:
        return seed_vals[0]
    return None

def preserve_seed(target_url: str, current_url: str) -> str:
    seed = extract_seed(current_url)
    if seed is None:
        return target_url
    target_seed = extract_seed(target_url)
    if target_seed == seed:
        return target_url
    parts = urlsplit(target_url)
    params = parse_qsl(parts.query)
    params = [(k, v) for (k, v) in params if k != 'seed']
    params.append(('seed', seed))
    new_query = urlencode(params)
    new_url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    return new_url

def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = parts.hostname
    if hostname and hostname not in _LOCALHOST_HOSTS:
        port = parts.port
        if port:
            new_netloc = f'localhost:{port}'
        else:
            new_netloc = 'localhost'
        return urlunsplit((parts.scheme, new_netloc, parts.path, parts.query, parts.fragment))
    return url

def is_localhost_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        return False
    hostname = parts.hostname
    if hostname is None:
        return False
    return hostname in _LOCALHOST_HOSTS