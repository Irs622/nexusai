"""Side-effect execution semantics classification for NexusAI tools and runtime engine."""

from __future__ import annotations

from enum import Enum

from nexusai.core.annotations import stable


@stable
class ExecutionSemantics(str, Enum):
    """Side-effect semantics classification determining safety of automated tool retries.

    Semantics:
        IDEMPOTENT: Safe to retry automatically with identical arguments; produces identical state/result
                    (e.g., read_file, git_status, database queries).
        DEDUPLICATED: Tool internally deduplicates operations using client-supplied or generated idempotency
                      keys (e.g., payment API calls with Idempotency-Key).
        TRANSACTIONAL: Tool execution supports atomic rollback upon failure
                       (e.g., transactional database writes, staged file operations).
        AT_LEAST_ONCE: Tool invocation cannot be guaranteed idempotent and may produce side effects or duplicates
                       if retried (e.g., send_email, post_webhook). Requires explicit confirmation or approval
                       for HIGH/CRITICAL risk operations prior to retry.
    """

    IDEMPOTENT = "idempotent"
    DEDUPLICATED = "deduplicated"
    TRANSACTIONAL = "transactional"
    AT_LEAST_ONCE = "at_least_once"

    @property
    def is_safe_for_auto_retry(self) -> bool:
        """Return True if this semantic classification permits automatic retries without human approval."""
        return self in (ExecutionSemantics.IDEMPOTENT, ExecutionSemantics.DEDUPLICATED)
