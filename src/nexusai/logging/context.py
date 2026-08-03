"""Async-Safe Observability Correlation Context using contextvars."""
import uuid
import contextvars
from typing import Optional, Dict

_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")
_workflow_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("workflow_id", default=None)
_plugin_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("plugin_id", default=None)

class CorrelationContext:
    """Async-safe context manager using Python contextvars."""

    @staticmethod
    def get_correlation_id() -> str:
        cid = _correlation_id_var.get()
        if not cid:
            cid = str(uuid.uuid4())
            _correlation_id_var.set(cid)
        return cid

    @staticmethod
    def set_context(correlation_id: Optional[str] = None, workflow_id: Optional[str] = None, plugin_id: Optional[str] = None) -> None:
        _correlation_id_var.set(correlation_id or str(uuid.uuid4()))
        if workflow_id:
            _workflow_id_var.set(workflow_id)
        if plugin_id:
            _plugin_id_var.set(plugin_id)

    @staticmethod
    def to_dict() -> Dict[str, str]:
        return {
            "correlation_id": CorrelationContext.get_correlation_id(),
            "workflow_id": _workflow_id_var.get() or "none",
            "plugin_id": _plugin_id_var.get() or "none",
        }
