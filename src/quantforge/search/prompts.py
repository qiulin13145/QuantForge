"""Build proposer context for proposals, verdict responses, and new residuals."""

import json
from typing import Any

from ..protocol import Program, ProposalPhase, ProposalRequest, Residual, SearchState
from ..schemas import PROPOSAL_SCHEMA, RESIDUAL_SCHEMA, RESPONSE_SCHEMA

PROPOSAL_INSTRUCTION = (
    "Propose executable Python code, competing explanations and pre-registered "
    "categorical predictions. Specify each condition's cost as a positive integer "
    "number of evaluator calls. A control is a complete Python source and should "
    "differ only by its stated intervention. The first explanation is the focal "
    "one. Return a JSON object matching the schema."
)

RESPONSE_INSTRUCTION = (
    "Implement the required verdict response in the targeted function. Return a "
    "changed complete Python program matching the schema."
)

RESIDUAL_INSTRUCTION = (
    "Use the remeasurement of the revised program to propose the next actionable "
    "design question, with a new unique ID, targeted function and probe input. "
    "Return a JSON object matching the schema."
)

INSTRUCTIONS = {
    "proposal": PROPOSAL_INSTRUCTION,
    "response": RESPONSE_INSTRUCTION,
    "residual": RESIDUAL_INSTRUCTION,
}
SCHEMAS = {
    "proposal": PROPOSAL_SCHEMA,
    "response": RESPONSE_SCHEMA,
    "residual": RESIDUAL_SCHEMA,
}


def build_request(
    phase: ProposalPhase,
    state: SearchState,
    parent: Program,
    residual: Residual,
    extra: dict[str, Any],
) -> ProposalRequest:
    """Attach the task, parent, question, and ten most recent round records."""
    context = {
        "phase": phase,
        "contract": state["config"]["contract"],
        "parent_source": parent["source"],
        "parent_score": parent["score"],
        "residual": residual,
        "history": state["history"][-10:],
        **extra,
    }
    return {
        "prompt": INSTRUCTIONS[phase] + "\n\n" + json.dumps(context, indent=2),
        "json_schema": SCHEMAS[phase],
        "phase": phase,
        "context": context,
    }
