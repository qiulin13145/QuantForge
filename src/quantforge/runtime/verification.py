"""Check that the response changes and executes the targeted computation."""

import ast
import difflib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from ..protocol import ContractError, ProbeResult


def _scope(source: str, name: str) -> ast.FunctionDef:
    """Locate the single synchronous top-level function targeted by a residual."""
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise ContractError(f"invalid candidate source: {exc}") from exc
    matches = [
        x
        for x in module.body
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name
    ]
    if len(matches) != 1 or isinstance(matches[0], ast.AsyncFunctionDef):
        raise ContractError(
            f"expected exactly one synchronous top-level function {name!r}"
        )
    return matches[0]


def check_response(
    parent: str, child: str, scope: str, probe_input: Any, timeout: int = 30
) -> ProbeResult:
    """Require a structural change and execution of a changed target line.

    The evaluator separately checks whether that execution satisfies the
    task-specific response to the verdict.
    """
    before, after = _scope(parent, scope), _scope(child, scope)
    if ast.dump(before, include_attributes=False) == ast.dump(
        after, include_attributes=False
    ):
        raise ContractError("response does not change the targeted function")
    changes = set()
    for tag, _, _, start, end in difflib.SequenceMatcher(
        a=parent.splitlines(), b=child.splitlines()
    ).get_opcodes():
        if tag in ("insert", "replace"):
            changes.update(range(start + 1, end + 1))
    changes &= set(range(after.lineno, after.end_lineno + 1))
    worker = Path(__file__).with_name("probe_worker.py")
    try:
        proc = subprocess.run(
            [sys.executable, str(worker)],
            input=json.dumps(
                {"source": child, "scope": scope, "probe_input": probe_input}
            ),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ContractError("targeted probe timed out") from exc
    if proc.returncode:
        raise ContractError(f"targeted probe failed: {proc.stderr[-2000:]}")
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("targeted probe returned invalid JSON") from exc
    reached = sorted(changes.intersection(report["lines"]))
    if not reached:
        raise ContractError(
            "the probe did not execute changed lines in the targeted function"
        )
    return {
        "scope": scope,
        "executed_changed_lines": reached,
        "output": report["output"],
    }
