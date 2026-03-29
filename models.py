from __future__ import annotations
from typing import Any
from pydantic import BaseModel

class Selector(BaseModel):
    type: str
    attribute: str | None = None
    value: str
    case_sensitive: bool = False

class Candidate(BaseModel):
    index: int
    tag: str
    text: str
    selector: Selector
    input_type: str | None = None
    name: str | None = None
    placeholder: str | None = None
    href: str | None = None
    role: str | None = None
    group: str = 'PAGE'
    container_chain: list[str] = []
    context: str = ''
    options: list[str] = []

class PageContext(BaseModel):
    url: str
    title: str = ''
    headings: list[str] = []

class PageIR(BaseModel):
    context: PageContext
    candidates: list[Candidate]
    raw_text: str = ''

class Constraint(BaseModel):
    field: str
    operator: str
    value: Any

class ActionRecord(BaseModel):
    action_type: str
    selector_value: str
    url: str
    step_index: int

class TaskState(BaseModel):
    task_id: str
    history: list[ActionRecord] = []
    filled_fields: set[str] = set()
    constraints: list[Constraint] = []
    task_type: str = 'general'
    credentials: dict[str, str] = {}
    prev_candidates: list | None = None
    memory: str = ''
    next_goal: str = ''
    prev_url: str = ''
    prev_summary: str = ''
    prev_digest: str = ''
    prev_sig_set: set[str] = set()
    model_config = {'arbitrary_types_allowed': True}