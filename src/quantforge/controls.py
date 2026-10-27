"""Compile the minimum-cost set of controls separating all explanations."""

from itertools import combinations
import math


class ContractError(ValueError):
    """Malformed, inconsistent, or incomplete experiment contract."""


def validate_and_select(proposal):
    if not isinstance(proposal, dict) or not isinstance(proposal.get("source"), str):
        raise ContractError("proposal must include a Python source string")
    explanations = proposal.get("explanations")
    if not isinstance(explanations, list) or len(explanations) < 2:
        raise ContractError("at least two competing explanations are required")
    ids = [x.get("id") if isinstance(x, dict) else None for x in explanations]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ContractError("explanation IDs must be nonempty and unique")
    conditions = proposal.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ContractError("conditions are required")
    names = []
    for item in conditions:
        if not isinstance(item, dict) or item.get("kind") not in ("primary", "control"):
            raise ContractError("condition kind must be primary or control")
        name = item.get("id")
        if not isinstance(name, str) or not name or name in names:
            raise ContractError("condition IDs must be nonempty and unique")
        names.append(name)
        cost = item.get("cost")
        if isinstance(cost, bool) or not isinstance(cost, (float, int)) or not math.isfinite(cost) or cost <= 0:
            raise ContractError("condition costs must be finite and positive")
        predictions = item.get("predictions")
        if not isinstance(predictions, dict) or set(predictions) != set(ids) or any(not isinstance(v, str) or not v for v in predictions.values()):
            raise ContractError("each condition requires a categorical prediction for each explanation")
        if item["kind"] == "control" and not isinstance(item.get("source"), str):
            raise ContractError("a control must contain its executable source")
    primaries = [x for x in conditions if x["kind"] == "primary"]
    if len(primaries) != 1:
        raise ContractError("exactly one primary is required")
    controls = [x for x in conditions if x["kind"] == "control"]
    if len(controls) > 16:
        raise ContractError("at most 16 controls are supported by the exhaustive compiler")
    pairs = list(combinations(ids, 2))
    unresolved = [(a, b) for a, b in pairs if primaries[0]["predictions"][a] == primaries[0]["predictions"][b]]
    choices = []
    for n in range(len(controls) + 1):
        for subset in combinations(controls, n):
            if all(any(c["predictions"][a] != c["predictions"][b] for c in subset) for a, b in unresolved):
                choices.append((sum(c["cost"] for c in subset), len(subset), tuple(sorted(c["id"] for c in subset)), subset))
    if not choices:
        raise ContractError("allowed controls cannot distinguish the explanations")
    selected = min(choices, key=lambda x: x[:3])[3]
    return [primaries[0], *selected]


def verdict(proposal, conditions, results, parent_score, direction="min"):
    """Separate observed program gain from the explanation-level verdict."""
    if any(results[c["id"]].get("safe") is not True or results[c["id"]].get("success") is not True for c in conditions):
        return "UNSAFE", False
    primary = results[conditions[0]["id"]]
    improved = primary["score"] < parent_score if direction == "min" else primary["score"] > parent_score
    signature = primary["signature"]
    if primary.get("parent_equivalent") is True:
        return "NO_EFFECT", False
    focal = proposal["explanations"][0]["id"]
    competitors = [e["id"] for e in proposal["explanations"][1:]]
    matches = all(results[c["id"]]["outcome"] == c["predictions"][focal] for c in conditions)
    excludes = all(any(results[c["id"]]["outcome"] != c["predictions"][other] for c in conditions) for other in competitors)
    resolved = matches and excludes
    if improved and signature and resolved:
        return "SUPPORTED", True
    if improved and not signature:
        return "TARGET_ONLY", True
    if signature and resolved:
        return "MEDIATOR_ONLY", False
    return "UNRESOLVED", improved
