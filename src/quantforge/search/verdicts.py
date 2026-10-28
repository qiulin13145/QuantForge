"""Interpret experimental evidence and specify the next program response."""

from typing import cast

from ..protocol import (
    Condition,
    Direction,
    EvaluationResult,
    Proposal,
    RequiredResponse,
    Verdict,
)

RESPONSES: dict[Verdict, RequiredResponse] = {
    "SUPPORTED": "EXTEND_OR_COMPOSE",
    "TARGET_ONLY": "REPAIR_EXPLANATION",
    "MEDIATOR_ONLY": "REPAIR_TRANSFER",
    "UNRESOLVED": "ADD_DISCRIMINATOR",
    "NO_EFFECT": "RETIRE_INTERVENTION",
    "UNSAFE": "RESTORE_PARENT",
}


def verdict(
    proposal: Proposal,
    conditions: list[Condition],
    results: dict[str, EvaluationResult],
    parent_score: float,
    direction: Direction = "min",
) -> tuple[Verdict, bool]:
    """Return the evidence verdict and whether the candidate should be retained.

    Support requires a gain, the target signature, and outcomes that match the
    focal explanation while excluding its competitors. A gain can still be
    retained when the explanation remains unresolved. NO_EFFECT requires an
    explicit equivalence observation from the evaluator.
    """
    if any(
        results[c["id"]].get("safe") is not True
        or results[c["id"]].get("success") is not True
        for c in conditions
    ):
        return "UNSAFE", False
    primary = results[conditions[0]["id"]]
    score = cast(float, primary["score"])
    improved = score < parent_score if direction == "min" else score > parent_score
    signature = primary["signature"]
    if primary.get("parent_equivalent") is True:
        return "NO_EFFECT", False
    focal = proposal["explanations"][0]["id"]
    competitors = [e["id"] for e in proposal["explanations"][1:]]
    matches = all(
        results[c["id"]]["outcome"] == c["predictions"][focal] for c in conditions
    )
    excludes = all(
        any(results[c["id"]]["outcome"] != c["predictions"][other] for c in conditions)
        for other in competitors
    )
    resolved = matches and excludes
    if improved and signature and resolved:
        return "SUPPORTED", True
    if improved and not signature:
        return "TARGET_ONLY", True
    if signature and resolved:
        return "MEDIATOR_ONLY", False
    return "UNRESOLVED", improved
