#!/usr/bin/env python3
"""Deterministic proposer for the CPU integration example; no model is called."""
import json
import sys


def main():
    request = json.load(sys.stdin)
    namespace = {}
    exec(request["context"]["parent_source"], namespace)
    offset = namespace["run"](0)
    if request["phase"] == "response":
        response = {"source": f"def run(x):\n    return x + {offset + 2}\n"}
    elif request["phase"] == "residual":
        assert "remeasurement" in request["context"]
        response = {"id": f"next-residual-{offset + 2}", "question": "Can the next change improve the result?",
                    "scope": "run", "probe_input": 1}
    else:
        response = {
            "source": f"def run(x):\n    return x + {offset + 1}\n",
            "explanations": [
                {"id": "targeted", "claim": "The targeted change yields the gain."},
                {"id": "alternative", "claim": "The gain persists without the targeted change."},
            ],
            "conditions": [
                {"id": "primary", "kind": "primary", "cost": 1,
                 "predictions": {"targeted": "gain", "alternative": "gain"}},
                {"id": "control", "kind": "control", "cost": 1,
                 "source": request["context"]["parent_source"],
                 "predictions": {"targeted": "loss", "alternative": "gain"}},
            ],
        }
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
