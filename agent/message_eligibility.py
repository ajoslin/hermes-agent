"""Cycle-safe predicates for durable, completed conversation messages."""

from __future__ import annotations

from typing import Any


EPHEMERAL_SCAFFOLDING_FLAGS = (
    "_empty_recovery_synthetic",
    "_empty_terminal_sentinel",
    "_thinking_prefill",
    "_verification_stop_synthetic",
    "_pre_verify_synthetic",
    "_kanban_stop_synthetic",
    "_dropped_toolcall_nudge",
)

# Hermes normalizes provider terminal completion reasons to ``stop`` before
# storing assistant messages. Missing reasons remain accepted for legacy and
# SessionDB-projected messages, whose durable shape may not retain this field.
EXPLICIT_TERMINAL_ASSISTANT_FINISH_REASONS = frozenset({"stop"})
INTERRUPTED_REDIRECT_API_PREFIX = "[This response was interrupted by a user correction.]"


def is_ephemeral_scaffolding(message: Any) -> bool:
    """Return whether *message* is internal retry/control scaffolding."""
    return isinstance(message, dict) and any(
        message.get(flag) for flag in EPHEMERAL_SCAFFOLDING_FLAGS
    )


def is_completed_assistant_message(message: Any) -> bool:
    """Return whether *message* is completed visible assistant final-answer text."""
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return False
    if is_ephemeral_scaffolding(message) or message.get("tool_calls"):
        return False
    if message.get("_interrupted_redirect_checkpoint"):
        return False
    api_content = message.get("api_content")
    if isinstance(api_content, str) and api_content.startswith(
        INTERRUPTED_REDIRECT_API_PREFIX
    ):
        return False
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return False
    finish_reason = message.get("finish_reason")
    if finish_reason is None:
        return True
    if not isinstance(finish_reason, str):
        return False
    return finish_reason.strip().lower() in EXPLICIT_TERMINAL_ASSISTANT_FINISH_REASONS
