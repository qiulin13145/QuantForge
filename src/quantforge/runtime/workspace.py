"""Atomic workspace state and single-writer coordination."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator

from ..protocol import ContractError, SearchState, validate_residual


def load(path: str | Path) -> Any:
    """Read a JSON configuration or workspace state without transforming it."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: str | Path, value: Any) -> None:
    """Flush state to a sibling temporary file, then atomically replace it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def lock(workspace: str | Path) -> Iterator[None]:
    """Allow one writer per workspace; fail immediately if another holds it."""
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    with (workspace / ".lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("workspace is already in use") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def digest(value: Any) -> str:
    """Hash the canonical JSON representation used by calls and experiments."""
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(data).hexdigest()


def initialize(workspace: str | Path, config_path: str | Path) -> Path:
    """Create a version-1 state with the initial program and its open question."""
    workspace, config_path = Path(workspace), Path(config_path).resolve()
    config = load(config_path)
    if not isinstance(config, dict):
        raise ContractError("configuration must be a JSON object")
    validate_residual(config.get("initial_residual"))
    if not isinstance(config.get("contract"), dict) or config.get(
        "direction", "min"
    ) not in ("min", "max"):
        raise ContractError("contract and objective direction are required")
    if type(config.get("budget")) is not int or config["budget"] < 1:
        raise ContractError("budget must be a positive integer")
    for name in ("proposer", "evaluator"):
        command = config.get(name)
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(x, str) or not x for x in command)
        ):
            raise ContractError(f"{name} must be a nonempty command array")
    source_path = (config_path.parent / config["initial_program"]).resolve()
    source = source_path.read_text(encoding="utf-8")
    with lock(workspace):
        state_path = workspace / "state.json"
        if state_path.exists():
            raise ContractError("workspace already initialized")
        config["config_dir"] = str(config_path.parent)
        state: SearchState = {
            "version": 1,
            "config": config,
            "spent": 0,
            "round": 0,
            "programs": [{"id": "initial", "source": source, "score": None}],
            "residuals": [
                {
                    **config["initial_residual"],
                    "program_id": "initial",
                    "status": "OPEN",
                }
            ],
            "history": [],
            "pending": None,
            "in_flight": None,
        }
        save(state_path, state)
    return state_path


def recover(workspace: str | Path) -> None:
    """Clear an interrupted call marker while keeping its budget charge."""
    workspace = Path(workspace)
    with lock(workspace):
        state = load(workspace / "state.json")
        if not state["in_flight"]:
            raise ContractError("no interrupted call")
        state["in_flight"] = None
        save(workspace / "state.json", state)


def retry_failed(workspace: str | Path, key: str) -> None:
    """Remove one cached error so the next step can issue a fresh call."""
    workspace = Path(workspace)
    with lock(workspace):
        state = load(workspace / "state.json")
        calls = (state.get("pending") or {}).get("calls", {})
        if state.get("in_flight") or key not in calls or "error" not in calls[key]:
            raise ContractError("no failed call with that key")
        del calls[key]
        save(workspace / "state.json", state)


def abort_round(workspace: str | Path) -> None:
    """Abandon the pending round and its staged candidate, retaining spending."""
    workspace = Path(workspace)
    with lock(workspace):
        state = load(workspace / "state.json")
        pending = state.get("pending")
        if state.get("in_flight") or not pending:
            raise ContractError("no idle pending round to abandon")
        staged_id = f"round-{pending['round']}-candidate"
        state["programs"] = [p for p in state["programs"] if p["id"] != staged_id]
        state["history"].append({"round": pending["round"], "status": "ABANDONED"})
        state["pending"] = None
        save(workspace / "state.json", state)
