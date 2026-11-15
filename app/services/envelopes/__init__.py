"""Envelope workflow services.

:class:`EnvelopeOrchestrator` composes the prepared → sealed → persisted
state transition in one authoritative place. CLI commands and internal
operator workflows delegate to it; no HTTP endpoint invokes it directly.
"""
from .orchestrator import (
    EnvelopeOrchestrator,
    FinalizeResult,
    OrchestratorError,
)

__all__ = ["EnvelopeOrchestrator", "FinalizeResult", "OrchestratorError"]
