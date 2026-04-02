from __future__ import annotations
import ctypes
import json
import os

def _v3_hash(value: str) -> int:
    h = 0
    for ch in value:
        h = (h << 5) - h + ord(ch)
        h = ctypes.c_int32(h).value
    return abs(h)
_VARIANTS: dict[str, dict[str, list[str]]] = {}
_data_path = os.path.join(os.path.dirname(__file__), 'data', 'v3_id_variants.json')
try:
    with open(_data_path, 'r', encoding='utf-8') as f:
        _VARIANTS = json.load(f)
except Exception:
    pass

def v3_id(seed: str | int | None, website: str | None, key: str) -> str:
    if not website or not key:
        return key
    site_variants = _VARIANTS.get(website, {})
    variants = site_variants.get(key)
    if not variants:
        return key
    seed_int = int(seed) if seed else 1
    if seed_int == 1 or len(variants) <= 1:
        return variants[0]
    idx = _v3_hash(f'{key}:{seed_int}') % len(variants)
    return variants[idx]