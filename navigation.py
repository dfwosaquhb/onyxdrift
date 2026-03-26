"""Navigation safety layer for SN36 Web Agent.

Handles seed preservation, URL normalization, and localhost restriction.
These are critical safety functions: violating seed or host rules = instant score 0.

NAV-01: extract_seed() - Extract seed from URL query params
NAV-02: preserve_seed() - Inject seed into NavigateAction URLs
NAV-04: normalize_url(), is_localhost_url() - URL host validation
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode, parse_qsl

# Allowed localhost hostnames (the sandbox only allows these)
_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Allowed URL schemes
_ALLOWED_SCHEMES = {"http", "https"}


def extract_seed(url: str) -> str | None:
    """Extract the seed parameter from a URL.

    Returns the seed value as a string, or None if not present.
    The evaluator uses ?seed=NNN to select data variants on demo websites.
    """
    if not url:
        return None
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    seed_vals = params.get("seed")
    if seed_vals:
        return seed_vals[0]
    return None


def preserve_seed(target_url: str, current_url: str) -> str:
    """Ensure the target URL contains the seed from the current URL.

    If current_url has a seed and target_url does not, adds it.
    If target_url already has the seed, does not duplicate it.
    If current_url has no seed, returns target_url unchanged.

    Critical: Missing or mismatched seed = instant score 0.
    """
    seed = extract_seed(current_url)
    if seed is None:
        return target_url

    # Check if target already has the correct seed
    target_seed = extract_seed(target_url)
    if target_seed == seed:
        return target_url

    # Parse target URL and update/add seed param
    parts = urlsplit(target_url)
    # Use parse_qsl to preserve param ordering
    params = parse_qsl(parts.query)

    # Remove any existing seed params (prevent duplicates/mismatches)
    params = [(k, v) for k, v in params if k != "seed"]
    # Add the correct seed
    params.append(("seed", seed))

    new_query = urlencode(params)
    new_url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    return new_url


def normalize_url(url: str) -> str:
    """Rewrite non-localhost URLs to localhost while preserving port/path/query.

    The evaluator rewrites URLs to localhost before sending to the agent.
    This function ensures any URLs the agent produces also use localhost.
    127.0.0.1 and ::1 are kept as-is (both are valid localhost).
    """
    parts = urlsplit(url)
    hostname = parts.hostname

    if hostname and hostname not in _LOCALHOST_HOSTS:
        # Rebuild netloc with localhost but preserve port
        port = parts.port
        if port:
            new_netloc = f"localhost:{port}"
        else:
            new_netloc = "localhost"
        return urlunsplit((parts.scheme, new_netloc, parts.path, parts.query, parts.fragment))

    return url


def is_localhost_url(url: str) -> bool:
    """Check if a URL is a valid localhost URL.

    Returns True only for http(s) URLs targeting localhost, 127.0.0.1, or ::1.
    Blocks: external hosts, javascript:, data:, file:, and other schemes.

    The sandbox evaluator blocks non-localhost NavigateAction URLs for demo webs.
    """
    parts = urlsplit(url)

    # Check scheme
    if parts.scheme not in _ALLOWED_SCHEMES:
        return False

    # Check hostname
    hostname = parts.hostname
    if hostname is None:
        return False

    return hostname in _LOCALHOST_HOSTS
