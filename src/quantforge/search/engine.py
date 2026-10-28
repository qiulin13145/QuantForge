"""Coordinate one durable round of evidence-guided program evolution.

Each stage reads and updates the same workspace state. Backend results are
persisted before advancing so a resumed round can reuse completed calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..protocol import (
    Condition,
    ContractError,
    EvaluationResult,
    ExperimentPacket,
    PendingRound,
    ProbeResult,
    Program,
    Proposal,
    ProposalPhase,
    Residual,
    Revision,
    RoundRecord,
    SearchState,
    Verdict,
    validate_residual,
)
from ..runtime.backend_runner import backend_identity, evaluate, invoke
from ..runtime.verification import check_response
from ..runtime.workspace import digest, load, lock, save
from .controls import validate_and_select
from .prompts import build_request
from .verdicts import RESPONSES, verdict


@dataclass(frozen=True)
class _RoundSession:
    """References to the parent, question, and pending calls of a locked round."""

    workspace: Path
    state: SearchState
    pending: PendingRound
    parent: Program
    residual: Residual

    def save(self) -> None:
        save(self.workspace / "state.json", self.state)

    def propose(
        self, key: str, phase: ProposalPhase, extra: dict[str, Any]
    ) -> dict[str, Any]:
        request = build_request(phase, self.state, self.parent, self.residual, extra)
        return invoke(self.workspace, self.state, key, "proposer", request)


def run_round(workspace: str | Path) -> RoundRecord:
    """Run or resume one round under the workspace's exclusive writer lock."""
    workspace = Path(workspace)
    with lock(workspace):
        session = _resume_or_start_round(workspace)
        _ensure_parent_evaluated(session)
        proposal, conditions = _request_valid_proposal(session)
        packet = _freeze_experiment(session, proposal, conditions)
        results = _evaluate_conditions(session, packet)
        record = _assess_evidence(session, packet, results)

        # Empirical improvement and support for an explanation are independent.
        _retain_candidate_if_improved(session, packet, record)
        if record["verdict"] not in ("NO_EFFECT", "UNSAFE"):
            response = _request_revision(session, proposal, record)
            proof, checked = _verify_revision(session, packet, response, record)
            measured = _remeasure_revision(session, response)
            descendant_id = _update_frontiers(
                session, proposal, response, measured, record
            )
            record.update(
                probe=proof,
                probe_evaluation=checked,
                descendant_id=descendant_id,
                remeasurement=measured,
            )

        return _finalize_round(session, record)


def _resume_or_start_round(workspace: Path) -> _RoundSession:
    state: SearchState = load(workspace / "state.json")
    if state.get("in_flight"):
        raise ContractError(
            "interrupted call detected; use recover after inspecting the external process"
        )
    if state["pending"] is None:
        residual = next(
            (item for item in state["residuals"] if item["status"] == "OPEN"), None
        )
        if not residual:
            raise ContractError("no open residual")
        state["pending"] = {
            "round": state["round"] + 1,
            "residual_id": residual["id"],
            "program_id": residual["program_id"],
            "calls": {},
        }
        save(workspace / "state.json", state)

    pending = state["pending"]
    parent = next(p for p in state["programs"] if p["id"] == pending["program_id"])
    residual = next(r for r in state["residuals"] if r["id"] == pending["residual_id"])
    return _RoundSession(workspace, state, pending, parent, residual)


def _ensure_parent_evaluated(session: _RoundSession) -> None:
    if session.parent["score"] is not None:
        return
    baseline = evaluate(
        session.workspace,
        session.state,
        "baseline",
        session.parent["source"],
        {"id": "baseline", "kind": "primary"},
    )
    if not baseline["success"] or not baseline["safe"]:
        raise ContractError("baseline evaluation failed")
    session.parent["score"] = baseline["score"]
    session.save()


def _request_valid_proposal(
    session: _RoundSession,
) -> tuple[Proposal, list[Condition]]:
    """Allow up to three designs before spending calls on their conditions."""
    feedback: dict[str, Any] = {}
    for attempt in range(3):
        key = "proposal" if attempt == 0 else f"proposal:{attempt + 1}"
        proposal = cast(Proposal, session.propose(key, "proposal", feedback))
        try:
            conditions = validate_and_select(proposal)
            if any(type(condition["cost"]) is not int for condition in conditions):
                raise ContractError(
                    "condition cost must be an integer number of evaluator calls"
                )
        except ContractError as exc:
            if attempt == 2:
                raise
            feedback = {"proposal_feedback": str(exc), "previous_proposal": proposal}
        else:
            return proposal, conditions
    raise AssertionError("proposal attempts must return or raise")


def _freeze_experiment(
    session: _RoundSession, proposal: Proposal, conditions: list[Condition]
) -> ExperimentPacket:
    """Bind predictions, source, task contract, and evaluator before execution."""
    packet: ExperimentPacket = {
        "parent_id": session.parent["id"],
        "parent_source_hash": digest(session.parent["source"]),
        "residual_id": session.residual["id"],
        "contract": session.state["config"]["contract"],
        "proposal": proposal,
        "conditions": conditions,
        "evaluator": backend_identity(session.state["config"], "evaluator"),
    }
    packet_hash = digest(packet)
    if (
        "packet_hash" in session.pending
        and session.pending["packet_hash"] != packet_hash
    ):
        raise ContractError("experiment packet changed after freezing")
    session.pending["packet_hash"] = packet_hash
    session.pending["packet"] = packet
    session.save()
    return packet


def _evaluate_conditions(
    session: _RoundSession, packet: ExperimentPacket
) -> dict[str, EvaluationResult]:
    results: dict[str, EvaluationResult] = {}
    for condition in packet["conditions"]:
        source = (
            packet["proposal"]["source"]
            if condition["kind"] == "primary"
            else condition["source"]
        )
        result = evaluate(
            session.workspace,
            session.state,
            "condition:" + condition["id"],
            source,
            condition,
            costs=condition["cost"],
        )
        results[condition["id"]] = result
        if not result["success"] or not result["safe"]:
            break
    return results


def _assess_evidence(
    session: _RoundSession,
    packet: ExperimentPacket,
    results: dict[str, EvaluationResult],
) -> RoundRecord:
    outcome: Verdict
    if len(results) != len(packet["conditions"]):
        outcome, improved = "UNSAFE", False
    else:
        outcome, improved = verdict(
            packet["proposal"],
            packet["conditions"],
            results,
            cast(float, session.parent["score"]),
            session.state["config"].get("direction", "min"),
        )
    return {
        "round": session.pending["round"],
        "parent_id": session.parent["id"],
        "residual_id": session.residual["id"],
        "packet_hash": session.pending["packet_hash"],
        "packet": packet,
        "verdict": outcome,
        "response": RESPONSES[outcome],
        "conditions": results,
        "retained_candidate": improved,
    }


def _retain_candidate_if_improved(
    session: _RoundSession, packet: ExperimentPacket, record: RoundRecord
) -> None:
    if not record["retained_candidate"]:
        return
    candidate_id = f"round-{session.pending['round']}-candidate"
    if any(p["id"] == candidate_id for p in session.state["programs"]):
        return
    primary = packet["conditions"][0]
    session.state["programs"].append(
        {
            "id": candidate_id,
            "source": packet["proposal"]["source"],
            "score": record["conditions"][primary["id"]]["score"],
            "parent_id": session.parent["id"],
        }
    )
    session.save()


def _request_revision(
    session: _RoundSession, proposal: Proposal, record: RoundRecord
) -> Revision:
    response = session.propose(
        "response",
        "response",
        {
            "candidate_source": proposal["source"],
            "verdict": record["verdict"],
            "required_response": record["response"],
            "conditions": record["conditions"],
        },
    )
    if not isinstance(response.get("source"), str):
        raise ContractError("response must include executable source")
    return cast(Revision, response)


def _run_execution_probe(
    session: _RoundSession, candidate_source: str, revised_source: str
) -> ProbeResult:
    """Persist the local trace separately from the task evaluator's check."""
    key = "probe"
    if key in session.pending["calls"]:
        cached = session.pending["calls"][key]
        if "error" in cached:
            raise ContractError(f"probe failed: {cached['error']}")
        return cached["result"]

    session.state["in_flight"] = {"key": key, "cost": 0}
    session.save()
    try:
        proof = check_response(
            candidate_source,
            revised_source,
            session.residual["scope"],
            session.residual["probe_input"],
            session.state["config"].get("timeout_seconds", 300),
        )
    except ContractError as exc:
        session.pending["calls"][key] = {"error": str(exc)}
        session.state["in_flight"] = None
        session.save()
        raise
    session.pending["calls"][key] = {"result": proof}
    session.state["in_flight"] = None
    session.save()
    return proof


def _verify_revision(
    session: _RoundSession,
    packet: ExperimentPacket,
    response: Revision,
    record: RoundRecord,
) -> tuple[ProbeResult, EvaluationResult]:
    """Require both an executed code change and the task's response check."""
    proof = _run_execution_probe(
        session, packet["proposal"]["source"], response["source"]
    )
    condition = {
        "id": "response_probe",
        "kind": "probe",
        "verdict": record["verdict"],
        "required_response": record["response"],
        "candidate_source": packet["proposal"]["source"],
        "primary_condition": packet["conditions"][0],
        "residual": session.residual,
        "explanations": packet["proposal"]["explanations"],
        "results": record["conditions"],
        "probe": proof,
    }
    checked = evaluate(
        session.workspace,
        session.state,
        "response_probe",
        response["source"],
        condition,
        phase="probe",
    )
    if (
        not checked["success"]
        or not checked["safe"]
        or checked.get("response_valid") is not True
    ):
        raise ContractError("the evaluator did not confirm the verdict response")
    return proof, checked


def _remeasure_revision(session: _RoundSession, response: Revision) -> EvaluationResult:
    measured = evaluate(
        session.workspace,
        session.state,
        "remeasurement",
        response["source"],
        {"id": "remeasurement", "kind": "primary"},
        phase="measurement",
    )
    if not measured["success"] or not measured["safe"]:
        raise ContractError("descendant measurement failed")
    return measured


def _update_frontiers(
    session: _RoundSession,
    proposal: Proposal,
    response: Revision,
    measured: EvaluationResult,
    record: RoundRecord,
) -> str | None:
    """Open the next question only after a non-regressing revision is measured."""
    direction = session.state["config"].get("direction", "min")
    score = cast(float, measured["score"])
    parent_score = cast(float, session.parent["score"])
    good = score <= parent_score if direction == "min" else score >= parent_score
    if not good:
        return None
    next_residual = cast(
        Residual,
        session.propose(
            "next_residual",
            "residual",
            {
                "candidate_source": proposal["source"],
                "revised_source": response["source"],
                "verdict": record["verdict"],
                "conditions": record["conditions"],
                "remeasurement": measured,
            },
        ),
    )
    validate_residual(next_residual)
    if any(r["id"] == next_residual["id"] for r in session.state["residuals"]):
        raise ContractError("next residual id already exists")

    descendant_id = f"round-{session.pending['round']}-response"
    session.state["programs"].append(
        {
            "id": descendant_id,
            "source": response["source"],
            "score": measured["score"],
            "parent_id": session.parent["id"],
        }
    )
    # An unresolved explanation stays open even when its program improves.
    if record["verdict"] != "UNRESOLVED":
        session.residual["status"] = (
            "CLOSED" if record["verdict"] == "SUPPORTED" else "REFRAMED"
        )
    session.state["residuals"].append(
        {**next_residual, "program_id": descendant_id, "status": "OPEN"}
    )
    return descendant_id


def _finalize_round(session: _RoundSession, record: RoundRecord) -> RoundRecord:
    session.state["history"].append(record)
    session.state["round"] = session.pending["round"]
    session.state["pending"] = None
    session.save()
    return record
