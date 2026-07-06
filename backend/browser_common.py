"""Shared, provider-agnostic parsing helpers for LLM browser-automation responses."""
from __future__ import annotations

import re


def clean_json_raw(raw: str) -> str:
    """
    Best-effort cleanup of an LLM's raw text response before JSON parsing.

    Handles several edge cases:
    - ```json ... ``` code fences
    - Nested backtick wrapping from HTML-to-markdown conversion: ```\n`{...}`\n```
    - Leading/trailing whitespace or explanation text
    """
    raw = raw.strip()

    # Strip outer triple-backtick code fences (with or without language tag)
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```\s*$', '', raw)
    raw = raw.strip()

    # Strip single backtick wrapping produced by pre/code DOM handling
    if raw.startswith('`') and raw.endswith('`'):
        raw = raw[1:-1].strip()

    # If there's still surrounding noise, extract the first {...} JSON object
    if not raw.startswith('{'):
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            raw = match.group(0)

    return raw


def parse_hook_sections(raw: str, max_points: int) -> tuple[dict[str, list[str]], str]:
    """
    Parse a '[HOOK]\\n...\\n\\n[Section Name]\\npoint1\\npoint2...' formatted
    LLM response into ({section_name: [points]}, hook_text).

    max_points caps how many bullet points are kept per section (5 for
    standard card points, 4 for newsletter variants).
    """
    result: dict[str, list[str]] = {}
    hook_text = ""
    current_name: str | None = None
    current_lines: list[str] = []
    is_hook = False

    for line in raw.splitlines():
        line = line.strip()
        header_match = re.match(r'^\[(.+)\]$', line)
        if header_match:
            if is_hook and current_lines:
                hook_text = current_lines[0]
            elif current_name is not None:
                result[current_name] = current_lines[:max_points]

            tag = header_match.group(1).strip()
            if tag == "HOOK":
                is_hook = True
                current_name = None
                current_lines = []
            else:
                is_hook = False
                current_name = tag
                current_lines = []
        elif line:
            cleaned = re.sub(r'^[\d]+[.、。\)）]\s*', '', line)
            cleaned = re.sub(r'^[-•·]\s*', '', cleaned).strip()
            if cleaned:
                current_lines.append(cleaned)

    if is_hook and current_lines:
        hook_text = current_lines[0]
    elif current_name is not None:
        result[current_name] = current_lines[:max_points]

    return result, hook_text
