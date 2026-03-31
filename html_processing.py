from __future__ import annotations
import re
from bs4 import BeautifulSoup, Comment
from config import SELECTOR_PRIORITY, PAGE_IR_CHAR_LIMIT
from models import Candidate, Selector, PageContext, PageIR

def _norm_ws(s: str) -> str:
    return re.sub('\\s+', ' ', s).strip()
STRIP_TAGS = {'script', 'style', 'svg', 'noscript', 'iframe'}
INTERACTIVE_CSS = "button, a[href], input:not([type='hidden']), textarea, select, [role='button'], [role='link'], [role='tab'], [role='menuitem']"
MAX_TEXT_LEN = 80

def prune_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, 'lxml')
    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    return soup
_CSS_HIDDEN_CLASSES = frozenset({'hidden', 'd-none', 'invisible', 'collapse', 'sr-only', 'visually-hidden', 'offscreen', 'screen-reader-only', 'display-none'})

def _is_hidden_or_disabled(element) -> bool:
    if element.has_attr('hidden'):
        return True
    if element.has_attr('disabled'):
        return True
    if element.get('type', '').lower() == 'hidden':
        return True
    style = element.get('style', '')
    if style:
        style_lower = style.lower().replace(' ', '')
        if 'display:none' in style_lower:
            return True
        if 'visibility:hidden' in style_lower:
            return True
        if 'opacity:0' in style_lower:
            return True
    if element.get('aria-hidden', '').lower() == 'true':
        return True
    classes = element.get('class', [])
    if isinstance(classes, list):
        class_set = {c.lower() for c in classes}
    else:
        class_set = {c.lower() for c in str(classes).split()}
    if class_set & _CSS_HIDDEN_CLASSES:
        return True
    parent = element.parent
    if parent and parent.name:
        parent_classes = parent.get('class', [])
        if isinstance(parent_classes, list):
            parent_set = {c.lower() for c in parent_classes}
        else:
            parent_set = {c.lower() for c in str(parent_classes).split()}
        if parent_set & _CSS_HIDDEN_CLASSES:
            return True
        parent_style = parent.get('style', '')
        if parent_style:
            ps = parent_style.lower().replace(' ', '')
            if 'display:none' in ps or 'visibility:hidden' in ps:
                return True
    return False

def _pick_selector(element) -> Selector | None:
    for attr in SELECTOR_PRIORITY:
        if attr == 'text':
            text = element.get_text(strip=True)
            if text:
                return Selector(type='tagContainsSelector', attribute=None, value=text[:50])
        else:
            val = element.get(attr)
            if val and isinstance(val, str) and val.strip():
                return Selector(type='attributeValueSelector', attribute=attr, value=val.strip())
    return None

def _classify_group(element) -> str:
    form = element.find_parent('form')
    if form is not None:
        fid = (form.get('id') or form.get('name') or '').strip()
        return f'FORM:{fid}' if fid else 'FORM'
    if element.find_parent('nav') is not None:
        return 'NAV'
    if element.find_parent('header') is not None:
        return 'HEADER'
    if element.find_parent('footer') is not None:
        return 'FOOTER'
    return 'PAGE'
_STRUCTURAL_TAGS = frozenset({'header', 'nav', 'main', 'form', 'section', 'article', 'aside', 'footer', 'ul', 'ol', 'table', 'div'})
_CONTEXT_CONTAINER_TAGS = frozenset({'li', 'tr', 'article', 'section', 'div', 'td'})

def _pick_context_container(el):
    try:
        candidates = []
        cur = el
        for _depth in range(8):
            if cur is None:
                break
            try:
                cur = cur.parent
            except Exception:
                break
            if cur is None:
                break
            tag = str(getattr(cur, 'name', '') or '')
            if tag not in _CONTEXT_CONTAINER_TAGS:
                continue
            try:
                txt_raw = cur.get_text('\n', strip=True)
            except Exception:
                txt_raw = ''
            length = len(txt_raw or '')
            if length <= 0:
                continue
            try:
                n_inter = len(cur.find_all(['a', 'button', 'input', 'select', 'textarea']))
            except Exception:
                n_inter = 0
            candidates.append((length, n_inter, cur))
        if not candidates:
            return None
        best = None
        best_key = None
        for (length, n_inter, node) in candidates:
            if not 50 <= length <= 900:
                continue
            if n_inter <= 0 or n_inter > 12:
                continue
            key = (length, n_inter)
            if best is None or key < (best_key or key):
                best = node
                best_key = key
        if best is not None:
            return best
        candidates.sort(key=lambda t: (t[0], t[1]))
        return candidates[0][2]
    except Exception:
        return None

def _container_chain_from_el(element) -> list[str]:
    chain: list[str] = []
    try:
        ancestors = list(element.parents) if hasattr(element, 'parents') else []
        for a in reversed(ancestors):
            try:
                tag = str(getattr(a, 'name', '') or '')
                if not tag or tag in {'[document]', 'html', 'body'}:
                    continue
                if tag not in _STRUCTURAL_TAGS:
                    continue
                aid = ''
                try:
                    aid = str(a.get('id') or a.get('name') or '').strip()
                except Exception:
                    aid = ''
                role = ''
                try:
                    role = str(a.get('role') or '').strip()
                except Exception:
                    role = ''
                heading = ''
                try:
                    h = a.find(['h1', 'h2', 'h3'])
                    if h is not None:
                        heading = _norm_ws(h.get_text(' ', strip=True))
                except Exception:
                    heading = ''
                label_bits = [tag]
                if aid:
                    label_bits.append(f'#{aid}')
                if role and role not in {'presentation'}:
                    label_bits.append(f'role={role}')
                if heading:
                    label_bits.append(heading[:50])
                label = ' '.join([b for b in label_bits if b])
                label = _norm_ws(label)
                if label and (not chain or chain[-1] != label):
                    chain.append(label)
                if len(chain) >= 4:
                    break
            except Exception:
                continue
    except Exception:
        return chain
    return chain[-3:]

def _extract_label_for_digest(soup, el) -> str:
    eid = el.get('id', '')
    if eid:
        label_el = soup.find('label', attrs={'for': eid})
        if label_el:
            return _norm_ws(label_el.get_text(' ', strip=True))
    parent_label = el.find_parent('label')
    if parent_label:
        return _norm_ws(parent_label.get_text(' ', strip=True))
    aria = el.get('aria-label', '')
    if aria:
        return _norm_ws(aria)
    ph = el.get('placeholder', '')
    if ph:
        return _norm_ws(ph)
    return ''

def build_dom_digest(soup: BeautifulSoup, limit: int=1400) -> str:
    parts: list[str] = []
    title = ''
    try:
        if soup.title and soup.title.get_text(strip=True):
            title = _norm_ws(soup.title.get_text(' ', strip=True))
    except Exception:
        title = ''
    if title:
        parts.append(f'TITLE: {title[:160]}')
    heads: list[str] = []
    for h in soup.find_all(['h1', 'h2', 'h3'], limit=12):
        t = _norm_ws(h.get_text(' ', strip=True))
        if t:
            heads.append(t[:140])
    if heads:
        parts.append('HEADINGS: ' + ' | '.join(heads[:12]))
    forms_bits: list[str] = []
    for form in soup.find_all('form', limit=4):
        els = form.find_all(['input', 'textarea', 'select'], limit=12)
        items: list[str] = []
        for el in els:
            try:
                itype = (el.get('type') or '').lower()
                if itype == 'hidden':
                    continue
                lbl = _extract_label_for_digest(soup, el)
                blob = ' '.join([lbl, el.get('name', ''), el.get('id', ''), el.get('placeholder', ''), el.get('aria-label', ''), itype]).strip()
                blob = _norm_ws(blob)
                if not blob:
                    continue
                items.append(blob[:140])
            except Exception:
                continue
        if items:
            forms_bits.append('; '.join(items[:8]))
    if forms_bits:
        parts.append('FORMS: ' + ' || '.join(forms_bits[:4]))
    ctas: list[str] = []
    for el in soup.select("button,a[href],[role='button'],[role='link']"):
        try:
            if len(ctas) >= 14:
                break
            t = _norm_ws(el.get_text(' ', strip=True))
            if not t:
                t = _norm_ws(str(el.get('aria-label') or ''))
            if not t:
                continue
            t_l = t.lower()
            if t_l in {'home', 'logo'}:
                continue
            if t not in ctas:
                ctas.append(t[:90])
        except Exception:
            continue
    if ctas:
        parts.append('CTAS: ' + ' | '.join(ctas[:12]))
    out = '\n'.join(parts).strip()
    return out[:limit]

def extract_candidates(soup: BeautifulSoup) -> list[Candidate]:
    candidates: list[Candidate] = []
    index = 0
    for element in soup.select(INTERACTIVE_CSS):
        if _is_hidden_or_disabled(element):
            continue
        selector = _pick_selector(element)
        if selector is None:
            continue
        text = element.get_text(strip=True)[:MAX_TEXT_LEN]
        tag = element.name
        group = _classify_group(element)
        container_chain = _container_chain_from_el(element)
        context = ''
        try:
            parent = _pick_context_container(element)
            if parent is None:
                parent = element.find_parent(['li', 'tr', 'article', 'section', 'div'])
            if parent is not None:
                ctx_raw = parent.get_text('\n', strip=True)
                context = _norm_ws(ctx_raw)
                if len(context) > 180:
                    context = context[:177] + '...'
        except Exception:
            context = ''
        option_texts: list[str] = []
        if tag == 'select':
            try:
                for o in element.find_all('option')[:12]:
                    t = o.get_text(' ', strip=True)
                    if t:
                        option_texts.append(t)
            except Exception:
                pass
        if tag == 'select' and selector.type == 'tagContainsSelector' and option_texts:
            safe = option_texts[0].replace('"', "'")
            selector = Selector(type='attributeValueSelector', attribute='custom', value=f'select:has(option:has-text("{safe}"))')
        candidate = Candidate(index=index, tag=tag, text=text, selector=selector, input_type=element.get('type') if tag in ('input', 'button') else None, name=element.get('name'), placeholder=element.get('placeholder'), href=element.get('href') if tag == 'a' else None, role=element.get('role'), group=group, container_chain=container_chain, context=context, options=option_texts)
        candidates.append(candidate)
        index += 1
    return candidates

def _format_selector_display(selector: Selector) -> str:
    if selector.attribute == 'id':
        return f'#{selector.value}'
    elif selector.attribute == 'href':
        return f'href="{selector.value}"'
    elif selector.attribute == 'name':
        return f"[name='{selector.value}']"
    elif selector.attribute == 'data-testid':
        return f"[data-testid='{selector.value}']"
    elif selector.attribute == 'aria-label':
        return f'[aria-label="{selector.value}"]'
    elif selector.attribute == 'placeholder':
        return f'[placeholder="{selector.value}"]'
    elif selector.attribute == 'title':
        return f'[title="{selector.value}"]'
    elif selector.type == 'tagContainsSelector':
        return f'"{selector.value}"'
    else:
        return f'{selector.attribute}="{selector.value}"'

def _format_candidate_line(c: Candidate) -> str:
    sel_display = _format_selector_display(c.selector)
    parts = [f'[{c.index}]', c.tag]
    if c.input_type:
        parts.append(f'type={c.input_type}')
    if c.text:
        parts.append(f'"{c.text}"')
    parts.append(sel_display)
    return ' '.join(parts)

def extract_page_context(soup: BeautifulSoup, url: str) -> PageContext:
    title = ''
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    headings = []
    for h in soup.find_all(['h1', 'h2', 'h3']):
        text = h.get_text(strip=True)
        if text:
            headings.append(text)
        if len(headings) >= 10:
            break
    return PageContext(url=url, title=title, headings=headings)

def build_page_ir(soup: BeautifulSoup, url: str, candidates: list[Candidate]) -> PageIR:
    context = extract_page_context(soup, url)
    lines: list[str] = []
    lines.append(f'URL: {context.url}')
    if context.title:
        lines.append(f'Title: {context.title}')
    if context.headings:
        lines.append(f"Headings: {', '.join(context.headings[:5])}")
    lines.append('')
    lines.append('Interactive elements:')
    header_text = '\n'.join(lines)
    remaining_budget = PAGE_IR_CHAR_LIMIT - len(header_text) - 1
    kept_candidates: list[Candidate] = []
    candidate_lines: list[str] = []
    running_len = 0
    for c in candidates:
        line = _format_candidate_line(c)
        line_len = len(line) + 1
        if running_len + line_len > remaining_budget:
            break
        candidate_lines.append(line)
        kept_candidates.append(c)
        running_len += line_len
    raw_text = header_text + '\n' + '\n'.join(candidate_lines)
    return PageIR(context=context, candidates=kept_candidates, raw_text=raw_text)

def format_browser_state(candidates: list[Candidate], prev_candidates: list[Candidate] | None=None, char_limit: int=6400) -> str:

    class _TNode:
        __slots__ = ('name', 'children', 'items')

        def __init__(self, name: str) -> None:
            self.name = name
            self.children: dict[str, _TNode] = {}
            self.items: list[tuple[int, Candidate]] = []
    root = _TNode('ROOT')

    def _chain_for(c: Candidate) -> list[str]:
        ch = list(c.container_chain) if c.container_chain else []
        if not ch:
            g = (c.group or 'PAGE').strip() or 'PAGE'
            ch = [g]
        return [str(x)[:80] for x in ch if str(x).strip()][:3]
    for (i, c) in enumerate(candidates):
        node = root
        for part in _chain_for(c):
            if part not in node.children:
                node.children[part] = _TNode(part)
            node = node.children[part]
        node.items.append((i, c))
    prev_sigs: set[str] | None = None
    if prev_candidates is not None and len(prev_candidates) > 0:
        prev_sigs = set()
        for pc in prev_candidates:
            sig = f'{pc.selector.value}|{pc.text[:80]}'
            prev_sigs.add(sig)

    def _render(node: _TNode, indent: str='') -> list[str]:
        lines: list[str] = []
        for (i, c) in node.items:
            label = (c.text or '').strip()
            if not label:
                label = c.placeholder or ''
            label = str(label).strip()
            sig = f"{c.selector.value}|{(c.text or '')[:80]}"
            is_new = prev_sigs is not None and sig not in prev_sigs
            star = '* ' if is_new else ''
            attrs_bits: list[str] = []
            if c.selector.attribute == 'id':
                attrs_bits.append(f'id={c.selector.value[:60]}')
            if c.name:
                attrs_bits.append(f'name={c.name[:60]}')
            if c.input_type:
                attrs_bits.append(f'type={c.input_type[:60]}')
            if c.placeholder:
                attrs_bits.append(f'placeholder={c.placeholder[:60]}')
            if c.href:
                href_display = c.href[:60] if len(c.href) <= 60 else c.href[:57] + '...'
                attrs_bits.append(f'href={href_display}')
            if c.role:
                attrs_bits.append(f'role={c.role[:60]}')
            attrs_str = ' | ' + ', '.join(attrs_bits) if attrs_bits else ''
            ctx = ''
            if c.tag in {'a', 'button'} and c.context.strip():
                ctx = ' :: ' + _norm_ws(c.context)[:120]
            opt_str = ''
            if c.tag == 'select' and c.options:
                show = c.options[:8]
                remaining = len(c.options) - 8
                preview = ', '.join(show)
                if remaining > 0:
                    preview += f', +{remaining}'
                opt_str = f' [opts: {preview}]'
            lines.append(f'{indent}{star}[{i}]<{c.tag}>{label}</{c.tag}>{attrs_str}{ctx}{opt_str}')
        for (name, child) in node.children.items():
            lines.append(f'{indent}{name}:')
            lines.extend(_render(child, indent + '\t'))
        return lines
    rendered = _render(root, '')
    result = '\n'.join(rendered)
    if len(result) > char_limit:
        page_indices = []
        non_page_indices = []
        in_page = False
        for (idx, line) in enumerate(rendered):
            stripped = line.lstrip('\t')
            if stripped.startswith('PAGE:'):
                in_page = True
                non_page_indices.append(idx)
            elif not line.startswith('\t') and ':' in stripped and (not stripped.startswith('[')):
                in_page = False
                non_page_indices.append(idx)
            elif in_page:
                page_indices.append(idx)
            else:
                non_page_indices.append(idx)
        while page_indices and len('\n'.join((rendered[i] for i in sorted(non_page_indices + page_indices)))) > char_limit:
            page_indices.pop()
        keep = sorted(set(non_page_indices + page_indices))
        result = '\n'.join((rendered[i] for i in keep))
        if len(result) > char_limit:
            result = result[:char_limit]
    return result

def summarize_html(soup: BeautifulSoup) -> str:
    parts: list[str] = []
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        parts.append(f'Title: {_norm_ws(title_tag.string)[:100]}')
    headings = [_norm_ws(h.get_text()) for h in soup.find_all(['h1', 'h2', 'h3'])[:6] if h.get_text(strip=True)]
    if headings:
        parts.append(f"Headings: {', '.join((h[:60] for h in headings))}")
    forms = soup.find_all('form')
    if forms:
        parts.append(f'Forms: {len(forms)}')
    links = soup.find_all('a', href=True)
    parts.append(f'Links: {len(links)}')
    inputs = soup.find_all(['input', 'textarea', 'select'])
    if inputs:
        parts.append(f'Inputs: {len(inputs)}')
    return ' | '.join(parts) if parts else 'Empty page'