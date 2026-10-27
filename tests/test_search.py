import json
from pathlib import Path
import sys
import tempfile
import unittest

from quantforge.controls import ContractError, validate_and_select, verdict
from quantforge.engine import initialize, recover, run_round
from quantforge.storage import load, save
from quantforge.verification import check_response

FIXTURES = Path(__file__).parent / "fixtures"


def proposal():
    return {"source": "def run(x):\n    return x + 1\n", "explanations": [{"id": "f"}, {"id": "c"}], "conditions": [
        {"id": "primary", "kind": "primary", "cost": 1, "predictions": {"f": "gain", "c": "gain"}},
        {"id": "cheap", "kind": "control", "cost": 1, "source": "def run(x):\n    return x\n", "predictions": {"f": "loss", "c": "gain"}},
        {"id": "expensive", "kind": "control", "cost": 2, "source": "def run(x):\n    return x\n", "predictions": {"f": "loss", "c": "gain"}}]}


class SearchTests(unittest.TestCase):
    def test_minimum_cost_and_unidentifiable_proposals(self):
        p = proposal()
        self.assertEqual([c["id"] for c in validate_and_select(p)], ["primary", "cheap"])
        for c in p["conditions"]:
            c["predictions"] = {"f": "same", "c": "same"}
        with self.assertRaises(ContractError):
            validate_and_select(p)

    def test_unsafe_control_and_missing_signature(self):
        p = proposal()
        selected = validate_and_select(p)
        results = {"primary": {"safe": True, "success": True, "score": 1, "signature": True, "outcome": "gain"}, "cheap": {"safe": False, "success": True, "score": 2, "signature": False, "outcome": "loss"}}
        self.assertEqual(verdict(p, selected, results, 2)[0], "UNSAFE")
        results["cheap"]["safe"] = True
        results["primary"]["signature"] = False
        self.assertEqual(verdict(p, selected, results, 2)[0], "TARGET_ONLY")

    def test_probe_rejects_noop_and_unreached_change(self):
        before = "def run(x):\n    return x + 1\n"
        with self.assertRaises(ContractError):
            check_response(before, before, "run", 1)
        before = "def run(x):\n    if x < 0:\n        return x\n    return x + 1\n"
        dead = "def run(x):\n    if x < 0:\n        return x + 2\n    return x + 1\n"
        with self.assertRaises(ContractError):
            check_response(before, dead, "run", 1)

    def test_complete_round_and_local_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "initial.py").write_text("def run(x):\n    return x\n")
            config = {"initial_program": "initial.py", "initial_residual": {"id": "r0", "question": "What produces the gain?", "scope": "run", "probe_input": 1}, "contract": {"task": "example"}, "direction": "min", "budget": 10, "proposer": [sys.executable, str(FIXTURES / "proposer.py")], "evaluator": [sys.executable, str(FIXTURES / "evaluator.py")]}
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            workspace = root / "run"
            initialize(workspace, config_path)
            record = run_round(workspace)
            state = load(workspace / "state.json")
            self.assertEqual(record["verdict"], "SUPPORTED")
            self.assertTrue(record["probe"]["executed_changed_lines"])
            self.assertEqual(state["round"], 1)
            self.assertEqual(state["spent"], 5)
            self.assertIsNone(state["pending"])
            self.assertEqual(state["residuals"][-1]["status"], "OPEN")
            self.assertEqual(state["residuals"][-1]["program_id"], record["descendant_id"])
            second = run_round(workspace)
            self.assertEqual(second["verdict"], "SUPPORTED")
            state = load(workspace / "state.json")
            self.assertEqual(state["round"], 2)
            self.assertEqual(state["spent"], 9)

    def test_recovery_keeps_the_charged_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "initial.py").write_text("def run(x):\n    return x\n")
            config = {"initial_program": "initial.py", "initial_residual": {"id": "r0", "question": "What produces the gain?", "scope": "run", "probe_input": 1}, "contract": {}, "budget": 10, "proposer": [sys.executable, str(FIXTURES / "proposer.py")], "evaluator": [sys.executable, str(FIXTURES / "evaluator.py")]}
            path = root / "config.json"
            path.write_text(json.dumps(config))
            workspace = root / "run"
            initialize(workspace, path)
            state = load(workspace / "state.json")
            state["spent"] = 1
            state["in_flight"] = {"key": "baseline", "cost": 1}
            save(workspace / "state.json", state)
            with self.assertRaisesRegex(ContractError, "interrupted call"):
                run_round(workspace)
            recover(workspace)
            run_round(workspace)
            self.assertEqual(load(workspace / "state.json")["spent"], 6)


if __name__ == "__main__":
    unittest.main()
