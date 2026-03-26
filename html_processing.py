"""HTML processing pipeline for SN36 Web Agent.

Converts raw snapshot_html into a compact Page IR for the LLM:
  1. prune_html() - Strip non-interactive tags and comments
  2. extract_candidates() - Find interactive elements with best selectors
  3. build_page_ir() - Format as numbered list within token budget
  4. extract_page_context() - Extract URL, title, headings

Selector priority: id > data-testid > href > aria-label > name > placeholder > title > text
NEVER uses CSS class selectors (Tailwind breaks Playwright).
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Comment

from config import SELECTOR_PRIORITY, PAGE_IR_CHAR_LIMIT
from models import Candidate, Selector, PageContext, PageIR

# Tags to strip from HTML (non-interactive, waste tokens)
STRIP_TAGS = {"script", "style", "svg", "noscript", "iframe"}

# CSS selector for interactive elements
INTERACTIVE_CSS = (
    "button, a[href], input:not([type='hidden']), textarea, select, "
    "[role='button'], [role='link']"
)

# Max visible text length per candidate
MAX_TEXT_LEN = 80


def prune_html(html: str) -> BeautifulSoup:
    """Parse HTML and remove non-interactive tags and comments.

    Strips: script, style, svg, noscript, iframe, HTML comments.
    Returns the modified BeautifulSoup object.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove unwanted tags
    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    return soup


def _is_hidden_or_disabled(element) -> bool:
    """Check if an element should be filtered out (hidden/disabled)."""
    # hidden attribute
    if element.has_attr("hidden"):
        return True

    # disabled attribute
    if element.has_attr("disabled"):
        return True

    # type="hidden" (belt-and-suspenders with CSS selector)
    if element.get("type", "").lower() == "hidden":
        return True

    # style-based hiding
    style = element.get("style", "")
    if style:
        style_lower = style.lower().replace(" ", "")
        if "display:none" in style_lower:
            return True
        if "visibility:hidden" in style_lower:
            return True

    # aria-hidden="true"
    if element.get("aria-hidden", "").lower() == "true":
        return True

    return False


def _pick_selector(element) -> Selector | None:
    """Pick the best selector for an element based on SELECTOR_PRIORITY.

    Priority: id > data-testid > href > aria-label > name > placeholder > title > text
    NEVER uses CSS class attribute.

    Returns None if no usable selector can be found.
    """
    for attr in SELECTOR_PRIORITY:
        if attr == "text":
            # Fallback: use visible text content
            text = element.get_text(strip=True)
            if text:
                return Selector(
                    type="tagContainsSelector",
                    attribute=None,
                    value=text[:50],
                )
        else:
            val = element.get(attr)
            if val and isinstance(val, str) and val.strip():
                return Selector(
                    type="attributeValueSelector",
                    attribute=attr,
                    value=val.strip(),
                )

    return None


def extract_candidates(soup: BeautifulSoup) -> list[Candidate]:
    """Extract interactive elements from parsed HTML.

    Finds buttons, links, inputs, textareas, selects, and role=button/link elements.
    Filters out hidden/disabled elements. Assigns best selector per SELECTOR_PRIORITY.
    Returns candidates with sequential 0-based indexing.
    """
    candidates: list[Candidate] = []
    index = 0

    for element in soup.select(INTERACTIVE_CSS):
        # Filter hidden/disabled
        if _is_hidden_or_disabled(element):
            continue

        # Pick best selector
        selector = _pick_selector(element)
        if selector is None:
            # No usable selector and no text -- skip (useless to the LLM)
            continue

        text = element.get_text(strip=True)[:MAX_TEXT_LEN]
        tag = element.name

        candidate = Candidate(
            index=index,
            tag=tag,
            text=text,
            selector=selector,
            input_type=element.get("type") if tag in ("input", "button") else None,
            name=element.get("name"),
            placeholder=element.get("placeholder"),
            href=element.get("href") if tag == "a" else None,
            role=element.get("role"),
        )
        candidates.append(candidate)
        index += 1

    return candidates


def _format_selector_display(selector: Selector) -> str:
    """Format a selector for human-readable display in Page IR."""
    if selector.attribute == "id":
        return f"#{selector.value}"
    elif selector.attribute == "href":
        return f'href="{selector.value}"'
    elif selector.attribute == "name":
        return f"[name='{selector.value}']"
    elif selector.attribute == "data-testid":
        return f"[data-testid='{selector.value}']"
    elif selector.attribute == "aria-label":
        return f'[aria-label="{selector.value}"]'
    elif selector.attribute == "placeholder":
        return f'[placeholder="{selector.value}"]'
    elif selector.attribute == "title":
        return f'[title="{selector.value}"]'
    elif selector.type == "tagContainsSelector":
        return f'"{selector.value}"'
    else:
        return f'{selector.attribute}="{selector.value}"'


def _format_candidate_line(c: Candidate) -> str:
    """Format a single candidate as a numbered line for Page IR."""
    sel_display = _format_selector_display(c.selector)
    parts = [f"[{c.index}]", c.tag]

    if c.input_type:
        parts.append(f"type={c.input_type}")

    if c.text:
        parts.append(f'"{c.text}"')

    parts.append(sel_display)

    return " ".join(parts)


def extract_page_context(soup: BeautifulSoup, url: str) -> PageContext:
    """Extract page-level metadata: URL, title, and headings (h1-h3)."""
    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Headings (h1-h3, capped at 10)
    headings = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        text = h.get_text(strip=True)
        if text:
            headings.append(text)
        if len(headings) >= 10:
            break

    return PageContext(url=url, title=title, headings=headings)


def build_page_ir(
    soup: BeautifulSoup,
    url: str,
    candidates: list[Candidate],
) -> PageIR:
    """Build the Page IR (Intermediate Representation) for the LLM.

    Formats candidates as a numbered list within PAGE_IR_CHAR_LIMIT.
    If the total exceeds the budget, truncates from the end (removes
    lower-priority candidates at the bottom of the page).
    """
    context = extract_page_context(soup, url)

    # Build header
    lines: list[str] = []
    lines.append(f"URL: {context.url}")
    if context.title:
        lines.append(f"Title: {context.title}")
    if context.headings:
        lines.append(f"Headings: {', '.join(context.headings[:5])}")
    lines.append("")  # blank separator
    lines.append("Interactive elements:")

    header_text = "\n".join(lines)
    remaining_budget = PAGE_IR_CHAR_LIMIT - len(header_text) - 1  # -1 for newline

    # Format candidate lines, truncating if budget exceeded
    kept_candidates: list[Candidate] = []
    candidate_lines: list[str] = []
    running_len = 0

    for c in candidates:
        line = _format_candidate_line(c)
        line_len = len(line) + 1  # +1 for newline
        if running_len + line_len > remaining_budget:
            break
        candidate_lines.append(line)
        kept_candidates.append(c)
        running_len += line_len

    raw_text = header_text + "\n" + "\n".join(candidate_lines)

    return PageIR(
        context=context,
        candidates=kept_candidates,
        raw_text=raw_text,
    )
