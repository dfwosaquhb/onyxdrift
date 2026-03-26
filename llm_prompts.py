"""LLM prompt construction for SN36 Web Agent (LLM-02).

Builds structured system and user prompts for the action generation LLM call.
The system prompt defines the agent role and JSON output format.
The user prompt provides task context, page elements, step info, history,
constraints, website hints, playbook guidance, and warning sections.
"""

from __future__ import annotations


def build_system_prompt() -> str:
    """Build the system prompt defining the web agent role and output format.

    Returns a string instructing the LLM to act as a web automation agent
    that outputs structured JSON action decisions.
    """
    return (
        "You are a web automation agent. You analyze HTML pages and decide browser actions to complete tasks.\n"
        "\n"
        "Output format: respond with a single JSON object (no markdown, no explanation).\n"
        "Keys:\n"
        '  "action": one of "click", "type", "navigate", "scroll", "select_option", "wait"\n'
        '  "candidate_id": integer index from the Page Elements list (required for click, type, select_option)\n'
        '  "text": string to type or option to select (required for type, select_option)\n'
        '  "url": target URL (required for navigate -- must be localhost, must preserve ?seed= parameter)\n'
        '  "direction": "up" or "down" (for scroll, default "down")\n'
        "\n"
        "Rules:\n"
        "- Only reference candidate_id values that appear in the Page Elements list.\n"
        "- For login forms, use <username> and <password> as text values.\n"
        "- For navigate actions, always preserve the ?seed= parameter from the current URL.\n"
        "- Choose the single most effective action to make progress on the task.\n"
        "\n"
        "Respond with JSON only. No explanation, no markdown fencing."
    )


def build_user_prompt(
    prompt: str,
    page_ir_text: str,
    step_index: int,
    action_history: list[str],
    website: str | None,
    website_hint: str = "",
    constraints_block: str = "",
    playbook: str = "",
    loop_warning: str | None = None,
    stuck_warning: str | None = None,
    filled_fields: set[str] | None = None,
) -> str:
    """Build the user prompt with task context and page state.

    Structured in labeled sections for clear LLM comprehension.
    New parameters (website_hint, constraints_block, playbook, loop_warning,
    stuck_warning, filled_fields) all have defaults for backward compatibility.
    """
    history_text = "\n".join(f"  - {h}" for h in action_history) if action_history else "None yet"

    parts: list[str] = []

    # 1. Task
    parts.append(f"TASK: {prompt}")

    # 2. Website (with optional hint)
    website_line = f"WEBSITE: {website or 'unknown'}"
    if website_hint:
        website_line += f" ({website_hint})"
    parts.append(website_line)

    # 3. Step
    parts.append(f"STEP: {step_index} of 12")

    # 4. Constraints block (already formatted with header)
    if constraints_block:
        parts.append("")
        parts.append(constraints_block)

    # 5. Playbook
    if playbook:
        parts.append(f"\nPLAYBOOK: {playbook}")

    # 6. Loop warning
    if loop_warning:
        parts.append(f"\nWARNING: {loop_warning}")

    # 7. Stuck warning
    if stuck_warning:
        parts.append(f"\nWARNING: {stuck_warning}")

    # 8. Action history
    parts.append(f"\nACTION HISTORY:\n{history_text}")

    # 9. Filled fields
    if filled_fields:
        parts.append(f"\nFILLED FIELDS: {', '.join(sorted(filled_fields))}")

    # 10. Page elements
    parts.append(f"\nPAGE ELEMENTS:\n{page_ir_text}")

    # 11. Footer
    parts.append("\nChoose ONE action to make progress on the task. Do NOT repeat previous actions.")

    return "\n".join(parts)
