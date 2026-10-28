#!/usr/bin/env python3
"""A real numerical Block32 evaluator for QuantForge integration examples.

The calling framework runs this program as an independent subprocess.  The
candidate code executes with the evaluator's OS permissions; a subprocess is
not a security sandbox.  Use only trusted candidates or add external isolation.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import random
import sys
from typing import Any, Callable, Iterator, NamedTuple

LEVELS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)


def reference(values: list[float]) -> list[float]:
    """E2M1 nearest decoding, with E8M0 power-of-two shared scaling."""
    largest = max(abs(v) for v in values)
    exponent = (
        max(-127, min(127, math.floor(math.log2(largest)) - 2)) if largest else -127
    )
    scale = math.ldexp(1.0, exponent)
    return [
        math.copysign(
            min(LEVELS, key=lambda x: (abs(x - abs(v) / scale), -x)) * scale, v
        )
        for v in values
    ]


def legal_block(values: list[float]) -> bool:
    """Check existence of a single E8M0 scale explaining all E2M1 codes."""
    if len(values) != 32 or not all(math.isfinite(x) for x in values):
        return False
    maximum = max(map(abs, values))
    if maximum == 0:
        return True
    center = math.floor(math.log2(maximum))
    for exponent in range(max(-127, center - 3), min(127, center + 2) + 1):
        scale = math.ldexp(1.0, exponent)
        if all(
            any(
                math.isclose(abs(x), level * scale, rel_tol=1e-8, abs_tol=1e-40)
                for level in LEVELS
            )
            for x in values
        ):
            return True
    return False


class BlockMeasurements(NamedTuple):
    """Accumulated reconstruction errors before normalization by block size."""

    squared_error: float
    parent_squared_error: float
    absolute_error: float
    worst_block_mse: float
    changed: bool


def _validate_request(request: dict[str, Any]) -> tuple[int, int]:
    """Check the task envelope and return the deterministic input settings."""
    source = request["source"]
    condition = request["condition"]
    contract = request["contract"]
    phase = request["phase"]
    if not isinstance(source, str) or len(source) > 1_000_000:
        raise ValueError("source must be a Python source string of at most 1 MB")
    if not isinstance(condition, dict) or not isinstance(contract, dict):
        raise ValueError("condition and contract must be JSON objects")
    if phase not in ("evaluation", "probe", "measurement"):
        raise ValueError("phase must be evaluation, probe, or measurement")
    count = contract.get("num_blocks", 32)
    seed = contract.get("seed", 0)
    if type(count) is not int or not 1 <= count <= 10_000 or type(seed) is not int:
        raise ValueError("invalid num_blocks or seed")
    return count, seed


def _load_program(source: str, role: str) -> Callable:
    namespace = {"__name__": f"quantforge_{role}"}
    exec(compile(source, f"<quantforge-{role}>", "exec"), namespace)
    quantize = namespace.get("quantize")
    if not callable(quantize):
        raise ValueError(f"{role} must define quantize(values, condition)")
    return quantize


def _blocks(count: int, seed: int) -> Iterator[list[float]]:
    """Generate the same ordered inputs for the candidate and its parent."""
    rng = random.Random(seed)
    for index in range(count):
        yield [
            rng.gauss(0, 1) * (3.0 if (i + index) % 17 == 0 else 1.0) for i in range(32)
        ]


def _measure_blocks(
    candidate: Callable,
    parent: Callable,
    condition: dict[str, Any],
    count: int,
    seed: int,
) -> BlockMeasurements:
    total = baseline = absolute_error = worst_block_mse = 0.0
    changed = False
    for block in _blocks(count, seed):
        decoded = list(candidate(block.copy(), condition.copy()))
        if not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in decoded
        ):
            raise ValueError("candidate output must contain numbers")
        decoded = [float(x) for x in decoded]
        if not legal_block(decoded):
            raise ValueError(
                "candidate produced non-finite or invalid Block32 E2M1/E8M0 output"
            )
        ref = list(parent(block.copy(), {"id": "parent", "kind": "primary"}))
        if not legal_block(ref):
            raise ValueError("parent produced invalid Block32 output")
        block_error = sum((x - q) ** 2 for x, q in zip(block, decoded))
        total += block_error
        absolute_error += sum(abs(x - q) for x, q in zip(block, decoded))
        worst_block_mse = max(worst_block_mse, block_error / 32)
        baseline += sum((x - q) ** 2 for x, q in zip(block, ref))
        changed |= decoded != ref
    return BlockMeasurements(total, baseline, absolute_error, worst_block_mse, changed)


def _result(
    measurements: BlockMeasurements, count: int, seed: int, phase: str
) -> dict[str, Any]:
    score = measurements.squared_error / (count * 32)
    baseline_score = measurements.parent_squared_error / (count * 32)
    tolerance = max(1e-12, baseline_score * 1e-9)
    outcome = (
        "improved"
        if score < baseline_score - tolerance
        else "worse" if score > baseline_score + tolerance else "unchanged"
    )
    return {
        "success": True,
        "safe": True,
        "score": score,
        "outcome": outcome,
        "signature": measurements.changed,
        "parent_equivalent": not measurements.changed,
        "details": {
            "baseline_score": baseline_score,
            "mean_absolute_error": measurements.absolute_error / (count * 32),
            "worst_block_mse": measurements.worst_block_mse,
            "num_blocks": count,
            "seed": seed,
            "phase": phase,
        },
    }


def _response_valid(request: dict[str, Any], score: float) -> bool:
    """Compare a revision with the tested candidate under the same task."""
    condition = request["condition"]
    prior = evaluate(
        {
            "source": condition["candidate_source"],
            "parent_source": request["parent_source"],
            "condition": condition["primary_condition"],
            "contract": request["contract"],
            "phase": "evaluation",
        }
    )
    delta = score - prior["score"]
    return abs(delta) > 1e-12 and (condition["verdict"] != "SUPPORTED" or delta < 0)


def evaluate(request: dict[str, Any]) -> dict[str, Any]:
    """Execute a candidate, measure reconstruction, and check a probe response."""
    count, seed = _validate_request(request)

    # Candidate output is redirected so the wire protocol stays valid JSON.
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        candidate = _load_program(request["source"], "candidate")
        parent = _load_program(request["parent_source"], "parent")
        measurements = _measure_blocks(
            candidate, parent, request["condition"], count, seed
        )
    result = _result(measurements, count, seed, request["phase"])
    if request["phase"] == "probe":
        result["response_valid"] = _response_valid(request, result["score"])
    return result


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        result = evaluate(request)
    except Exception as exc:
        result = {
            "success": False,
            "safe": False,
            "score": None,
            "outcome": "error",
            "signature": False,
            "details": {"error": f"{type(exc).__name__}: {exc}"},
        }
    json.dump(result, sys.stdout, allow_nan=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
