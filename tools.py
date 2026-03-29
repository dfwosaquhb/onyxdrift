from __future__ import annotations
import re
from typing import Any
from bs4 import BeautifulSoup

def _norm_ws(s: str) -> str:
    return re.sub('\\s+', ' ', s).strip()

def _safe_truncate(s: str, n: int) -> str:
    s = str(s or '')
    return s if len(s) <= n else s[:max(0, n - 3)] + '...'

def _attrs_to_str_map(attrs: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for (k, v) in attrs.items():
        if isinstance(v, list):
            out[k] = ' '.join((str(x) for x in v))
        else:
            out[k] = str(v)
    return out

def tool_search_text(*, html: str, query: str, regex: bool=False, case_sensitive: bool=False, max_matches: int=20, context_chars: int=80) -> dict[str, Any]:
    q = str(query or '')
    if not q:
        return {'ok': False, 'error': 'missing query'}
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pat = re.compile(q if regex else re.escape(q), flags)
    except Exception as e:
        return {'ok': False, 'error': f'invalid pattern: {str(e)[:120]}'}
    hay = str(html or '')
    out: list[dict[str, Any]] = []
    for m in pat.finditer(hay):
        if len(out) >= int(max_matches):
            break
        a = max(0, m.start() - int(context_chars))
        b = min(len(hay), m.end() + int(context_chars))
        out.append({'start': m.start(), 'end': m.end(), 'snippet': _safe_truncate(hay[a:b].replace('\n', ' ').replace('\r', ' '), 2 * int(context_chars) + 40)})
    return {'ok': True, 'matches': out, 'count': len(out)}

def tool_css_select(*, html: str, selector: str, max_nodes: int=20) -> dict[str, Any]:
    sel = str(selector or '').strip()
    if not sel:
        return {'ok': False, 'error': 'missing selector'}
    try:
        soup = BeautifulSoup(html or '', 'html.parser')
        nodes = soup.select(sel)
    except Exception as e:
        return {'ok': False, 'error': f'css select failed: {str(e)[:160]}'}
    out: list[dict[str, Any]] = []
    for n in nodes[:int(max_nodes)]:
        try:
            tag = str(getattr(n, 'name', '') or '')
            attrs = _attrs_to_str_map(getattr(n, 'attrs', {}) or {})
            text = _norm_ws(n.get_text(' ', strip=True))
            out.append({'tag': tag, 'attrs': {k: _safe_truncate(v, 120) for (k, v) in list(attrs.items())[:12]}, 'text': _safe_truncate(text, 240)})
        except Exception:
            continue
    return {'ok': True, 'count': len(nodes), 'nodes': out}

def tool_xpath_select(*, html: str, xpath: str, max_nodes: int=20) -> dict[str, Any]:
    xp = str(xpath or '').strip()
    if not xp:
        return {'ok': False, 'error': 'missing xpath'}
    try:
        from lxml import etree
    except Exception:
        return {'ok': False, 'error': 'lxml not available'}
    try:
        doc = etree.HTML(html or '')
        nodes = doc.xpath(xp)
    except Exception as e:
        return {'ok': False, 'error': f'xpath failed: {str(e)[:160]}'}
    out: list[dict[str, Any]] = []
    for n in nodes[:int(max_nodes)]:
        try:
            if not hasattr(n, 'tag'):
                out.append({'value': _safe_truncate(str(n), 240)})
                continue
            tag = str(getattr(n, 'tag', '') or '')
            raw_attrib = getattr(n, 'attrib', {}) or {}
            attrs = {k: _safe_truncate(str(v), 120) for (k, v) in list(raw_attrib.items())[:12]}
            text = _norm_ws(' '.join(n.itertext()))
            out.append({'tag': tag, 'attrs': attrs, 'text': _safe_truncate(text, 240)})
        except Exception:
            continue
    return {'ok': True, 'count': len(nodes), 'nodes': out}

def tool_extract_forms(*, html: str, max_forms: int=10, max_inputs: int=25) -> dict[str, Any]:
    try:
        soup = BeautifulSoup(html or '', 'html.parser')
    except Exception as e:
        return {'ok': False, 'error': f'parse failed: {str(e)[:160]}'}
    forms: list[dict[str, Any]] = []
    for f in soup.find_all('form')[:int(max_forms)]:
        try:
            f_attrs = _attrs_to_str_map(getattr(f, 'attrs', {}) or {})
            controls: list[dict[str, Any]] = []
            for el in f.find_all(['input', 'textarea', 'select', 'button'])[:int(max_inputs)]:
                try:
                    tag = str(getattr(el, 'name', '') or '')
                    a = _attrs_to_str_map(getattr(el, 'attrs', {}) or {})
                    t = _norm_ws(el.get_text(' ', strip=True))
                    controls.append({'tag': tag, 'type': (a.get('type') or '').lower(), 'id': a.get('id') or '', 'name': a.get('name') or '', 'placeholder': a.get('placeholder') or '', 'aria_label': a.get('aria-label') or '', 'value': _safe_truncate(a.get('value') or '', 120), 'text': _safe_truncate(t, 160)})
                except Exception:
                    continue
            forms.append({'id': f_attrs.get('id') or '', 'name': f_attrs.get('name') or '', 'action': f_attrs.get('action') or '', 'method': (f_attrs.get('method') or '').upper(), 'controls': controls})
        except Exception:
            continue
    return {'ok': True, 'forms': forms, 'count': len(forms)}

def tool_visible_text(*, html: str, max_chars: int=2000) -> dict[str, Any]:
    try:
        soup = BeautifulSoup(html or '', 'html.parser')
        for t in soup(['script', 'style', 'noscript']):
            try:
                t.decompose()
            except Exception:
                pass
        txt = _norm_ws(soup.get_text(' ', strip=True))
        return {'ok': True, 'text': _safe_truncate(txt, int(max_chars))}
    except Exception as e:
        return {'ok': False, 'error': f'extract text failed: {str(e)[:160]}'}

def tool_list_candidates(*, candidates: list, max_n: int=80) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    for (i, c) in enumerate((candidates or [])[:int(max_n)]):
        sel_value = ''
        try:
            sel_value = c.selector.value if hasattr(c.selector, 'value') else str(c.selector)
        except Exception:
            pass
        out.append({'id': i, 'tag': getattr(c, 'tag', ''), 'group': getattr(c, 'group', 'PAGE'), 'text': _safe_truncate(getattr(c, 'text', '') or '', 140), 'context': _safe_truncate(getattr(c, 'context', '') or '', 200), 'selector_value': _safe_truncate(sel_value, 120)})
    return {'ok': True, 'count': len(candidates or []), 'candidates': out}

def tool_list_links(*, html: str, max_links: int=30) -> dict[str, Any]:
    try:
        soup = BeautifulSoup(html or '', 'html.parser')
    except Exception as e:
        return {'ok': False, 'error': f'parse failed: {str(e)[:160]}'}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.select('a[href]'):
        try:
            href = str(a.get('href') or '').strip()
            if not href or href.lower().startswith('javascript:'):
                continue
            text = _norm_ws(a.get_text(' ', strip=True))
            if not text:
                text = _norm_ws(str(a.get('aria-label') or ''))
            sig = href + '|' + text
            if sig in seen:
                continue
            seen.add(sig)
            out.append({'href': _safe_truncate(href, 260), 'text': _safe_truncate(text, 160)})
            if len(out) >= int(max_links):
                break
        except Exception:
            continue
    return {'ok': True, 'count': len(out), 'links': out}

def tool_list_cards(*, candidates: list, max_cards: int=6, max_text: int=200) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for (i, c) in enumerate(candidates or []):
        try:
            ctx = getattr(c, 'context', '') or ''
            ctx = str(ctx).strip()
            if not ctx:
                continue
            g = groups.get(ctx)
            if g is None:
                g = {'text_preview': _safe_truncate(ctx, int(max_text)), 'elements': []}
                groups[ctx] = g
            g['elements'].append({'candidate_id': i, 'tag': getattr(c, 'tag', ''), 'text': _safe_truncate(getattr(c, 'text', '') or '', 140)})
        except Exception:
            continue
    ranked = sorted(groups.values(), key=lambda g: (len(g.get('text_preview', '')), len(g.get('elements', []))), reverse=True)
    cards = ranked[:int(max_cards)]
    return {'ok': True, 'count': len(cards), 'cards': cards}
TOOL_REGISTRY = {'search_text': tool_search_text, 'css_select': tool_css_select, 'xpath_select': tool_xpath_select, 'extract_forms': tool_extract_forms, 'visible_text': tool_visible_text, 'list_candidates': tool_list_candidates, 'list_links': tool_list_links, 'list_cards': tool_list_cards}

def run_tool(tool_name: str, args: dict[str, Any], *, html: str, url: str, candidates: list) -> dict[str, Any]:
    t = str(tool_name or '').strip()
    fn = TOOL_REGISTRY.get(t)
    if fn is None:
        return {'ok': False, 'error': f'unknown tool: {t}'}
    a = args if isinstance(args, dict) else {}
    try:
        if t == 'list_candidates':
            safe_args = {k: v for (k, v) in a.items() if k in {'max_n'}}
            return fn(candidates=candidates, **safe_args)
        if t == 'list_cards':
            safe_args = {k: v for (k, v) in a.items() if k in {'max_cards', 'max_text'}}
            return fn(candidates=candidates, **safe_args)
        if t == 'list_links':
            safe_args = {k: v for (k, v) in a.items() if k in {'max_links'}}
            return fn(html=html, **safe_args)
        return fn(html=html, **a)
    except Exception as e:
        return {'ok': False, 'error': str(e)[:200]}