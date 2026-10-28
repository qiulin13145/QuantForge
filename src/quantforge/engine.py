"""Compatibility imports for the original search API.

The search controller lives in ``quantforge.search.engine``; workspace lifecycle
operations live in ``quantforge.runtime.workspace``.
"""

from .protocol import ContractError, validate_residual as _validate_residual
from .runtime.backend_runner import (
    backend_identity as _backend_identity,
    evaluate as _evaluation,
    invoke as _invoke,
    resolve_command as _command,
)
from .runtime.workspace import abort_round, digest, initialize, recover, retry_failed
from .schemas import PROPOSAL_SCHEMA, RESIDUAL_SCHEMA, RESPONSE_SCHEMA
from .search.engine import run_round
from .search.prompts import build_request as _prompt
from .search.verdicts import RESPONSES

__all__ = ["initialize", "run_round", "recover", "retry_failed", "abort_round"]
