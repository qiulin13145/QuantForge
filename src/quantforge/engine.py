"""Durable evidence-guided search loop."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from .controls import ContractError, validate_and_select, verdict
from .storage import load, lock, save
from .verification import check_response


RESPONSES = {"SUPPORTED": "EXTEND_OR_COMPOSE", "TARGET_ONLY": "REPAIR_EXPLANATION", "MEDIATOR_ONLY": "REPAIR_TRANSFER", "UNRESOLVED": "ADD_DISCRIMINATOR", "NO_EFFECT": "RETIRE_INTERVENTION", "UNSAFE": "RESTORE_PARENT"}
PROPOSAL_SCHEMA = {"type": "object", "required": ["source", "explanations", "conditions"], "properties": {"source": {"type": "string"}, "explanations": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "claim": {"type": "string"}}, "required": ["id", "claim"], "additionalProperties": False}}, "conditions": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "kind": {"type": "string", "enum": ["primary", "control"]}, "cost": {"type": "number"}, "source": {"type": "string"}, "predictions": {"type": "object", "additionalProperties": {"type": "string"}}}, "required": ["id", "kind", "cost", "predictions"], "additionalProperties": False}}}, "additionalProperties": False}
RESPONSE_SCHEMA = {"type": "object", "required": ["source", "next_residual"], "properties": {"source": {"type": "string"}, "next_residual": {"type": "object", "required": ["id", "question", "scope", "probe_input"], "properties": {"id": {"type": "string"}, "question": {"type": "string"}, "scope": {"type": "string"}, "probe_input": {}}, "additionalProperties": False}}, "additionalProperties": False}


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def _validate_residual(residual):
    if not isinstance(residual, dict) or any(not isinstance(residual.get(k), str) or not residual[k] for k in ("id", "question", "scope")) or "probe_input" not in residual:
        raise ContractError("residual requires id, question, scope and probe_input")


def initialize(workspace, config_path):
    workspace, config_path = Path(workspace), Path(config_path).resolve()
    config = load(config_path)
    if not isinstance(config, dict):
        raise ContractError("configuration must be a JSON object")
    _validate_residual(config.get("initial_residual"))
    if not isinstance(config.get("contract"), dict) or config.get("direction", "min") not in ("min", "max"):
        raise ContractError("contract and objective direction are required")
    if type(config.get("budget")) is not int or config["budget"] < 1:
        raise ContractError("budget must be a positive integer")
    for name in ("proposer", "evaluator"):
        command = config.get(name)
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
            raise ContractError(f"{name} must be a nonempty command array")
    source_path = (config_path.parent / config["initial_program"]).resolve()
    source = source_path.read_text(encoding="utf-8")
    with lock(workspace):
        state_path = workspace / "state.json"
        if state_path.exists():
            raise ContractError("workspace already initialized")
        config["config_dir"] = str(config_path.parent)
        state = {"version": 1, "config": config, "spent": 0, "round": 0, "programs": [{"id": "initial", "source": source, "score": None}], "residuals": [{**config["initial_residual"], "program_id": "initial", "status": "OPEN"}], "history": [], "pending": None, "in_flight": None}
        save(state_path, state)
    return state_path


def _command(config, name):
    return [x.replace("{config_dir}", config["config_dir"]) for x in config[name]]


def _backend_identity(config, name):
    command = _command(config, name)
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


def _invoke(workspace, state, key, name, request, *, costs=0):
    pending = state["pending"]
    request_hash = digest({"request": request, "backend": _backend_identity(state["config"], name)})
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
    command = _command(state["config"], name)
    try:
        proc = subprocess.run(command, input=json.dumps(request, allow_nan=False), capture_output=True, text=True, timeout=state["config"].get("timeout_seconds", 300), cwd=state["config"]["config_dir"], check=False)
        if proc.returncode:
            raise RuntimeError(f"{name} exited with status {proc.returncode}: {proc.stderr[-1000:]}")
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


def _evaluation(workspace, state, key, source, condition, phase="evaluation", costs=1):
    parent = next(p for p in state["programs"] if p["id"] == state["pending"]["program_id"])
    request = {"source": source, "parent_source": parent["source"], "parent_score": parent["score"], "condition": condition, "contract": state["config"]["contract"], "phase": phase}
    result = _invoke(workspace, state, key, "evaluator", request, costs=costs)
    if type(result.get("success")) is not bool or type(result.get("safe")) is not bool or type(result.get("signature")) is not bool or not isinstance(result.get("outcome"), str):
        raise ContractError(f"{key}: malformed evaluator result")
    if result["success"] and result["safe"] and (isinstance(result.get("score"), bool) or not isinstance(result.get("score"), (int, float)) or not math.isfinite(result["score"])):
        raise ContractError(f"{key}: score must be finite")
    return result


def _prompt(phase, state, parent, residual, extra):
    context = {"phase": phase, "contract": state["config"]["contract"], "parent_source": parent["source"], "parent_score": parent["score"], "residual": residual, "history": state["history"][-10:], **extra}
    instruction = ("Propose executable Python code, competing explanations and pre-registered categorical predictions. Specify each condition's cost as a positive integer number of evaluator calls. A control is a complete Python source and should differ only by its stated intervention. The first explanation is the focal one. Return a JSON object matching the schema." if phase == "proposal" else "Implement the required verdict response in the targeted function. Return a changed complete Python program and an actionable next residual with a new unique ID and a probe input. Return a JSON object matching the schema.")
    return {"prompt": instruction + "\n\n" + json.dumps(context, indent=2), "json_schema": PROPOSAL_SCHEMA if phase == "proposal" else RESPONSE_SCHEMA, "phase": phase, "context": context}


def run_round(workspace):
    workspace = Path(workspace)
    with lock(workspace):
        path = workspace / "state.json"
        state = load(path)
        if state.get("in_flight"):
            raise ContractError("interrupted call detected; use recover after inspecting the external process")
        if state["pending"] is None:
            residual = next((r for r in state["residuals"] if r["status"] == "OPEN"), None)
            if not residual:
                raise ContractError("no open residual")
            state["pending"] = {"round": state["round"] + 1, "residual_id": residual["id"], "program_id": residual["program_id"], "calls": {}}
            save(path, state)
        pending = state["pending"]
        parent = next(p for p in state["programs"] if p["id"] == pending["program_id"])
        residual = next(r for r in state["residuals"] if r["id"] == pending["residual_id"])
        if parent["score"] is None:
            base = _evaluation(workspace, state, "baseline", parent["source"], {"id": "baseline", "kind": "primary"})
            if not base["success"] or not base["safe"]:
                raise ContractError("baseline evaluation failed")
            parent["score"] = base["score"]
            save(path, state)
        proposal = _invoke(workspace, state, "proposal", "proposer", _prompt("proposal", state, parent, residual, {}))
        conditions = validate_and_select(proposal)
        if any(type(c["cost"]) is not int for c in conditions):
            raise ContractError("condition cost must be an integer number of evaluator calls")
        packet = {"parent_id": parent["id"], "parent_source_hash": digest(parent["source"]), "residual_id": residual["id"], "contract": state["config"]["contract"], "proposal": proposal, "conditions": conditions, "evaluator": _backend_identity(state["config"], "evaluator")}
        packet_hash = digest(packet)
        if "packet_hash" in pending and pending["packet_hash"] != packet_hash:
            raise ContractError("experiment packet changed after freezing")
        pending["packet_hash"] = packet_hash
        pending["packet"] = packet
        save(path, state)
        results = {}
        for condition in conditions:
            source = proposal["source"] if condition["kind"] == "primary" else condition["source"]
            results[condition["id"]] = _evaluation(workspace, state, "condition:" + condition["id"], source, condition, costs=condition["cost"])
            if not results[condition["id"]]["success"] or not results[condition["id"]]["safe"]:
                break
        if len(results) != len(conditions):
            outcome, improved = "UNSAFE", False
        else:
            outcome, improved = verdict(proposal, conditions, results, parent["score"], state["config"].get("direction", "min"))
        record = {"round": pending["round"], "parent_id": parent["id"], "residual_id": residual["id"], "packet_hash": packet_hash, "packet": packet, "verdict": outcome, "response": RESPONSES[outcome], "conditions": results, "retained_candidate": improved}
        if improved:
            candidate_id = f"round-{pending['round']}-candidate"
            if not any(p["id"] == candidate_id for p in state["programs"]):
                state["programs"].append({"id": candidate_id, "source": proposal["source"], "score": results[conditions[0]["id"]]["score"], "parent_id": parent["id"]})
                save(path, state)
        if outcome not in ("NO_EFFECT", "UNSAFE"):
            response = _invoke(workspace, state, "response", "proposer", _prompt("response", state, parent, residual, {"candidate_source": proposal["source"], "verdict": outcome, "required_response": RESPONSES[outcome], "conditions": results}))
            if not isinstance(response.get("source"), str):
                raise ContractError("response must include executable source")
            _validate_residual(response.get("next_residual"))
            if any(r["id"] == response["next_residual"]["id"] for r in state["residuals"]):
                raise ContractError("next residual id already exists")
            probe_key = "probe"
            if probe_key in pending["calls"]:
                if "error" in pending["calls"][probe_key]:
                    raise ContractError(f"probe failed: {pending['calls'][probe_key]['error']}")
                proof = pending["calls"][probe_key]["result"]
            else:
                state["in_flight"] = {"key": probe_key, "cost": 0}
                save(path, state)
                try:
                    proof = check_response(proposal["source"], response["source"], residual["scope"], residual["probe_input"], state["config"].get("timeout_seconds", 300))
                except ContractError as exc:
                    pending["calls"][probe_key] = {"error": str(exc)}
                    state["in_flight"] = None
                    save(path, state)
                    raise
                pending["calls"][probe_key] = {"result": proof}
                state["in_flight"] = None
                save(path, state)
            probe_condition = {"id": "response_probe", "kind": "probe", "verdict": outcome, "required_response": RESPONSES[outcome], "candidate_source": proposal["source"], "primary_condition": conditions[0], "probe": proof}
            checked = _evaluation(workspace, state, "response_probe", response["source"], probe_condition, phase="probe")
            if not checked["success"] or not checked["safe"] or checked.get("response_valid") is not True:
                raise ContractError("the evaluator did not confirm the verdict response")
            measured = _evaluation(workspace, state, "remeasurement", response["source"], {"id": "remeasurement", "kind": "primary"}, phase="measurement")
            if not measured["success"] or not measured["safe"]:
                raise ContractError("descendant measurement failed")
            descendant_id = f"round-{pending['round']}-response"
            good = measured["score"] <= parent["score"] if state["config"].get("direction", "min") == "min" else measured["score"] >= parent["score"]
            if good:
                state["programs"].append({"id": descendant_id, "source": response["source"], "score": measured["score"], "parent_id": parent["id"]})
                residual["status"] = "CLOSED" if outcome == "SUPPORTED" else "REFRAMED"
                state["residuals"].append({**response["next_residual"], "program_id": descendant_id, "status": "OPEN"})
            record.update({"probe": proof, "probe_evaluation": checked, "descendant_id": descendant_id if good else None, "remeasurement": measured})
        state["history"].append(record)
        state["round"] = pending["round"]
        state["pending"] = None
        save(path, state)
        return record


def recover(workspace):
    workspace = Path(workspace)
    with lock(workspace):
        state = load(workspace / "state.json")
        if not state["in_flight"]:
            raise ContractError("no interrupted call")
        state["in_flight"] = None
        save(workspace / "state.json", state)


def retry_failed(workspace, key):
    workspace = Path(workspace)
    with lock(workspace):
        state = load(workspace / "state.json")
        calls = (state.get("pending") or {}).get("calls", {})
        if state.get("in_flight") or key not in calls or "error" not in calls[key]:
            raise ContractError("no failed call with that key")
        del calls[key]
        save(workspace / "state.json", state)


def abort_round(workspace):
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
