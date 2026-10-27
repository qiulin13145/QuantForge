"""Evaluate a packing heuristic on a fixed set of integer instances."""

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import sys


def load_program(source):
    namespace = {"__name__": "quantforge_candidate"}
    exec(compile(source, "<candidate>", "exec"), namespace)
    fn = namespace.get("pack")
    if not callable(fn):
        raise ValueError("candidate must define pack(items, capacity)")
    return fn


def run_instance(fn, items, capacity):
    packed = fn(items.copy(), capacity)
    if not isinstance(packed, list) or any(not isinstance(b, list) or not b for b in packed):
        raise ValueError("pack must return a list of nonempty bins")
    if any(type(item) is not int for b in packed for item in b):
        raise ValueError("bin items must be integers")
    if Counter(item for b in packed for item in b) != Counter(items):
        raise ValueError("every input item must be packed exactly once")
    if any(sum(b) > capacity for b in packed):
        raise ValueError("a bin exceeds capacity")
    return packed


def evaluate(request):
    contract = request["contract"]
    capacity = contract["capacity"]
    instances = contract["instances"]
    if type(capacity) is not int or capacity <= 0 or not isinstance(instances, list) or not instances:
        raise ValueError("contract requires a positive integer capacity and instances")
    if any(not isinstance(items, list) or not items or any(type(x) is not int or x <= 0 or x > capacity for x in items) for items in instances):
        raise ValueError("instances must contain positive integer items within capacity")

    # Candidate code and print statements stay out of the JSON wire protocol.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        candidate = load_program(request["source"])
        parent = load_program(request["parent_source"])
        candidate_bins = [run_instance(candidate, items, capacity) for items in instances]
        parent_bins = [run_instance(parent, items, capacity) for items in instances]
        score = sum(map(len, candidate_bins)) / len(instances)
        parent_score = sum(map(len, parent_bins)) / len(instances)
        outcome = "gain" if score < parent_score else "loss" if score > parent_score else "unchanged"
        result = {"success": True, "safe": True, "score": score, "outcome": outcome,
                  "signature": candidate_bins != parent_bins,
                  "details": {"bins_per_instance": [len(b) for b in candidate_bins]}}

        if request["phase"] == "probe":
            condition = request["condition"]
            tested = load_program(condition["candidate_source"])
            probe_items = contract["probe_items"]
            before = run_instance(tested, probe_items, capacity)
            after = run_instance(candidate, probe_items, capacity)
            result["response_valid"] = bool(condition["probe"]["executed_changed_lines"]) and before != after
    return result


def main():
    try:
        result = evaluate(json.load(sys.stdin))
    except Exception as exc:
        result = {"success": False, "safe": False, "score": None, "outcome": "error",
                  "signature": False, "details": {"error": f"{type(exc).__name__}: {exc}"}}
    json.dump(result, sys.stdout, allow_nan=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
