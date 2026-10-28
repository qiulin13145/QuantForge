"""Execute JSON backends with durable call caching and budget accounting."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any, Literal, Mapping, cast

from ..protocol import (
    BackendIdentity,
    ContractError,
    EvaluationPhase,
    EvaluationRequest,
    EvaluationResult,
    PendingRound,
    SearchConfig,
    SearchState,
)
from .workspace import digest, save


def resolve_command(
    config: SearchConfig, name: Literal["proposer", "evaluator"]
) -> list[str]:
    """Expand configuration-relative paths without invoking a shell."""
    return [x.replace("{config_dir}", config["config_dir"]) for x in config[name]]


def backend_identity(
    config: SearchConfig, name: Literal["proposer", "evaluator"]
) -> BackendIdentity:
    """Fingerprint the configured command and file arguments for frozen calls."""
    command = resolve_command(config, name)
    files = {}
    for index, arg in enumerate(command):
        candidate = shutil.which(arg) if index == 0 else arg
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_absolute():
            path = Path(config["config_dir"]) / path
        if path.is_file():
            h = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    h.update(chunk)
            files[str(path.resolve())] = h.hexdigest()
    return {"command": command, "files": files}


def invoke(
    workspace: Path,
    state: SearchState,
    key: str,
    name: Literal["proposer", "evaluator"],
    request: Mapping[str, Any],
    *,
    costs: int = 0,
) -> dict[str, Any]:
    """Reuse a matching result or charge, execute, and persist one backend call.

    Charging precedes process execution. Recovery and retries therefore cannot
    silently restore evaluator calls already spent on an interrupted attempt.
    """
    pending = cast(PendingRound, state["pending"])
    request_hash = digest(
        {"request": request, "backend": backend_identity(state["config"], name)}
    )
    if key in pending["calls"]:
        cached = pending["calls"][key]
        if cached["request_hash"] != request_hash:
            raise ContractError(f"cached {key} request does not match the frozen input")
        if "error" in cached:
            raise ContractError(f"{key} failed: {cached['error']}")
        return cached["result"]
    if state["in_flight"]:
        raise ContractError("an interrupted call requires explicit recovery")
    if state["spent"] + costs > state["config"]["budget"]:
        raise ContractError("evaluator-call budget exhausted")
    state["spent"] += costs
    state["in_flight"] = {"key": key, "request_hash": request_hash, "cost": costs}
    save(workspace / "state.json", state)
    command = resolve_command(state["config"], name)
    try:
        proc = subprocess.run(
            command,
            input=json.dumps(request, allow_nan=False),
            capture_output=True,
            text=True,
            timeout=state["config"].get("timeout_seconds", 300),
            cwd=state["config"]["config_dir"],
            check=False,
        )
        if proc.returncode:
            raise RuntimeError(
                f"{name} exited with status {proc.returncode}: {proc.stderr[-1000:]}"
            )
        result = json.loads(proc.stdout)
        if not isinstance(result, dict):
            raise ValueError("backend response must be a JSON object")
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as exc:
        pending["calls"][key] = {"request_hash": request_hash, "error": str(exc)}
        state["in_flight"] = None
        save(workspace / "state.json", state)
        raise ContractError(f"{key} failed: {exc}") from exc
    pending["calls"][key] = {"request_hash": request_hash, "result": result}
    state["in_flight"] = None
    save(workspace / "state.json", state)
    return result


def evaluate(
    workspace: Path,
    state: SearchState,
    key: str,
    source: str,
    condition: Mapping[str, Any],
    phase: EvaluationPhase = "evaluation",
    costs: int = 1,
) -> EvaluationResult:
    """Send task inputs to the evaluator and check its response envelope."""
    parent = next(
        p
        for p in state["programs"]
        if p["id"] == cast(PendingRound, state["pending"])["program_id"]
    )
    request: EvaluationRequest = {
        "source": source,
        "parent_source": parent["source"],
        "parent_score": parent["score"],
        "condition": condition,
        "contract": state["config"]["contract"],
        "phase": phase,
    }
    result = invoke(workspace, state, key, "evaluator", request, costs=costs)
    if (
        type(result.get("success")) is not bool
        or type(result.get("safe")) is not bool
        or type(result.get("signature")) is not bool
        or not isinstance(result.get("outcome"), str)
    ):
        raise ContractError(f"{key}: malformed evaluator result")
    if "parent_equivalent" in result and type(result["parent_equivalent"]) is not bool:
        raise ContractError(f"{key}: parent_equivalent must be a boolean")
    if (
        result["success"]
        and result["safe"]
        and (
            isinstance(result.get("score"), bool)
            or not isinstance(result.get("score"), (int, float))
            or not math.isfinite(result["score"])
        )
    ):
        raise ContractError(f"{key}: score must be finite")
    return cast(EvaluationResult, result)
