"""Named final-report contracts for read-only scout delegations."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

_CONTRACT_HEADER = "SCOUT OUTPUT CONTRACT (machine-validated)"
_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


def coerce_required_outputs(raw: Any) -> Tuple[Optional[List[str]], Optional[str]]:
    """Return normalized output names or an actionable validation error."""
    if raw is None:
        return None, None
    if not isinstance(raw, list) or not raw:
        return None, "required_outputs must be a non-empty list of non-empty strings."

    outputs: List[str] = []
    seen = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            return None, "required_outputs must be a non-empty list of non-empty strings."
        name = item.strip()
        key = name.casefold()
        if key in seen:
            return None, f"required_outputs contains a duplicate name: {name!r}."
        seen.add(key)
        outputs.append(name)
    return outputs, None


def append_required_outputs_contract(context: Optional[str], outputs: List[str]) -> str:
    """Tell the scout which exact named sections its final report must contain."""
    names = "\n".join(f"- {name}" for name in outputs)
    block = (
        f"{_CONTRACT_HEADER}:\n"
        "Your FINAL response must contain one Markdown heading for every exact "
        "output name below. Put a substantive answer under each heading. The "
        "parent validates the headings and rejects missing or empty sections.\n"
        f"{names}"
    )
    base = (context or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def validate_required_outputs(text: str, outputs: List[str]) -> Tuple[bool, List[str]]:
    """Require every exact named heading to have non-empty section content."""
    raw = text or ""
    matches = list(_HEADING_RE.finditer(raw))
    sections = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip().casefold()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        sections.setdefault(name, raw[match.end() : end].strip())

    errors: List[str] = []
    for output in outputs:
        body = sections.get(output.casefold())
        if body is None:
            errors.append(f"Missing Markdown heading: {output}")
        elif not body:
            errors.append(f"Markdown section is empty: {output}")
    return not errors, errors


def build_required_outputs_retry_message(errors: List[str]) -> str:
    """Request one bounded correction without re-pasting the full task."""
    error_block = "\n".join(f"- {error}" for error in errors)
    return (
        "Your previous final response was rejected by the SCOUT OUTPUT "
        "CONTRACT validator. Validation errors:\n"
        f"{error_block}\n\n"
        "Reply with the corrected final report. Use every exact required output "
        "name as a Markdown heading and put a substantive answer under it."
    )
