"""Shared vocabulary for search, backend messages, and workspace state.

The records remain ordinary JSON-compatible dictionaries. Types document the
wire format without changing serialization or discarding task-specific fields.
Optional fields use TypedDict inheritance to support Python 3.10.
"""

from typing import Any, Literal, Mapping, TypedDict

Direction = Literal["min", "max"]
ProposalPhase = Literal["proposal", "response", "residual"]
EvaluationPhase = Literal["evaluation", "probe", "measurement"]
Verdict = Literal[
    "SUPPORTED", "TARGET_ONLY", "MEDIATOR_ONLY", "UNRESOLVED", "NO_EFFECT", "UNSAFE"
]
RequiredResponse = Literal[
    "EXTEND_OR_COMPOSE",
    "REPAIR_EXPLANATION",
    "REPAIR_TRANSFER",
    "ADD_DISCRIMINATOR",
    "RETIRE_INTERVENTION",
    "RESTORE_PARENT",
]


class ContractError(ValueError):
    """Malformed, inconsistent, or incomplete experiment contract."""


class _ProgramFields(TypedDict):
    id: str
    source: str
    score: float | None


class Program(_ProgramFields, total=False):
    """Executable program retained in the workspace's program frontier."""

    parent_id: str


class _ResidualFields(TypedDict):
    id: str
    question: str
    scope: str
    probe_input: Any


class Residual(_ResidualFields, total=False):
    """Design question, with ownership and status added when it is retained."""

    program_id: str
    status: Literal["OPEN", "CLOSED", "REFRAMED"]


class Explanation(TypedDict):
    """A proposed explanation; the first in a proposal is the focal one."""

    id: str
    claim: str


class _ConditionFields(TypedDict):
    id: str
    kind: Literal["primary", "control"]
    cost: int
    predictions: dict[str, str]


class Condition(_ConditionFields, total=False):
    """Pre-registered predictions and, for a control, executable source."""

    source: str


class Proposal(TypedDict):
    source: str
    explanations: list[Explanation]
    conditions: list[Condition]


class Revision(TypedDict):
    source: str


class _EvaluationFields(TypedDict):
    success: bool
    safe: bool
    score: float | None
    outcome: str
    signature: bool


class EvaluationResult(_EvaluationFields, total=False):
    """Task measurements, including optional equivalence and response checks."""

    parent_equivalent: bool
    response_valid: bool
    details: dict[str, Any]


class ProposalRequest(TypedDict):
    prompt: str
    json_schema: dict[str, Any]
    phase: ProposalPhase
    context: dict[str, Any]


class EvaluationRequest(TypedDict):
    source: str
    parent_source: str
    parent_score: float | None
    condition: Mapping[str, Any]
    contract: dict[str, Any]
    phase: EvaluationPhase


class BackendIdentity(TypedDict):
    command: list[str]
    files: dict[str, str]


class ExperimentPacket(TypedDict):
    """Frozen experiment inputs, used to detect changes during resumption."""

    parent_id: str
    parent_source_hash: str
    residual_id: str
    contract: dict[str, Any]
    proposal: Proposal
    conditions: list[Condition]
    evaluator: BackendIdentity


class ProbeResult(TypedDict):
    scope: str
    executed_changed_lines: list[int]
    output: Any


class _RoundFields(TypedDict):
    round: int
    parent_id: str
    residual_id: str
    packet_hash: str
    packet: ExperimentPacket
    verdict: Verdict
    response: RequiredResponse
    conditions: dict[str, EvaluationResult]
    retained_candidate: bool


class RoundRecord(_RoundFields, total=False):
    probe: ProbeResult
    probe_evaluation: EvaluationResult
    descendant_id: str | None
    remeasurement: EvaluationResult


class AbandonedRound(TypedDict):
    round: int
    status: Literal["ABANDONED"]


class CallRecord(TypedDict, total=False):
    """Persisted result or error; local execution probes have no request hash."""

    request_hash: str
    result: Any
    error: str


class _PendingFields(TypedDict):
    round: int
    residual_id: str
    program_id: str
    calls: dict[str, CallRecord]


class PendingRound(_PendingFields, total=False):
    packet_hash: str
    packet: ExperimentPacket


class _ConfigFields(TypedDict):
    initial_program: str
    initial_residual: Residual
    contract: dict[str, Any]
    budget: int
    proposer: list[str]
    evaluator: list[str]


class SearchConfig(_ConfigFields, total=False):
    direction: Direction
    timeout_seconds: int
    config_dir: str


class SearchState(TypedDict):
    version: int
    config: SearchConfig
    spent: int
    round: int
    programs: list[Program]
    residuals: list[Residual]
    history: list[RoundRecord | AbandonedRound]
    pending: PendingRound | None
    in_flight: dict[str, Any] | None


def validate_residual(residual: Any) -> None:
    """Require the actionable question, target function, and execution input."""
    if (
        not isinstance(residual, dict)
        or any(
            not isinstance(residual.get(key), str) or not residual[key]
            for key in ("id", "question", "scope")
        )
        or "probe_input" not in residual
    ):
        raise ContractError("residual requires id, question, scope and probe_input")
