"""Domain models for SN36 Web Agent.

Pydantic models for HTML processing pipeline: Selector, Candidate, PageContext, PageIR.
These form the data layer that all agent logic depends on.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Selector(BaseModel):
    """Element selector compatible with IWA action format.

    Maps to the Selector model in autoppia_iwa:
    - attributeValueSelector: targets by HTML attribute (id, name, href, etc.)
    - tagContainsSelector: targets by visible text content
    - xpathSelector: targets by XPath expression
    """

    type: str  # "attributeValueSelector", "tagContainsSelector", "xpathSelector"
    attribute: str | None = None
    value: str
    case_sensitive: bool = False


class Candidate(BaseModel):
    """An interactive element extracted from the page HTML.

    Each candidate represents a clickable, typeable, or selectable element
    that the agent can interact with. Candidates are numbered and presented
    to the LLM as a compact Page IR.
    """

    index: int
    tag: str  # "button", "a", "input", "textarea", "select", "div", etc.
    text: str  # visible text or label (truncated to 80 chars)
    selector: Selector
    input_type: str | None = None  # "text", "password", "email", "submit", etc.
    name: str | None = None  # HTML name attribute
    placeholder: str | None = None  # placeholder text
    href: str | None = None  # link href (for anchor elements)
    role: str | None = None  # ARIA role


class PageContext(BaseModel):
    """Page-level metadata extracted from the HTML."""

    url: str
    title: str = ""
    headings: list[str] = []  # h1-h3 text content


class PageIR(BaseModel):
    """Intermediate Representation of a web page for the LLM.

    Contains page context (URL, title, headings) and a numbered list of
    interactive elements (candidates). The raw_text field holds the
    formatted string sent to the LLM prompt.
    """

    context: PageContext
    candidates: list[Candidate]
    raw_text: str = ""  # formatted text representation for LLM prompt


class Constraint(BaseModel):
    """A parsed constraint from an IWA task prompt.

    Extracted from natural language task descriptions, e.g.:
    "price less than 10" -> Constraint(field="price", operator="less_than", value="10")
    """

    field: str
    operator: str  # equals, not_equals, contains, not_contains, greater_than, less_than, greater_equal, less_equal, in, not_in
    value: Any  # string or list (for in/not_in)


class ActionRecord(BaseModel):
    """A single action taken during a task."""

    action_type: str
    selector_value: str
    url: str
    step_index: int


class TaskState(BaseModel):
    """Per-task state tracking across multi-step evaluations."""

    task_id: str
    history: list[ActionRecord] = []
    filled_fields: set[str] = set()
    constraints: list[Constraint] = []
    task_type: str = "general"

    model_config = {"arbitrary_types_allowed": True}
