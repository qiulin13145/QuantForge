import json
from pathlib import Path
import sys
import tempfile
import unittest

from quantforge.controls import ContractError
from quantforge.engine import initialize, recover, run_round
from quantforge.storage import load, save

FIXTURES = Path(__file__).parent / "fixtures"


class SearchTests(unittest.TestCase):
    def test_complete_round_and_local_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "initial.py").write_text("def run(x):\n    return x\n")
            config = {
                "initial_program": "initial.py",
                "initial_residual": {
                    "id": "r0",
                    "question": "What produces the gain?",
                    "scope": "run",
                    "probe_input": 1,
                },
                "contract": {"task": "example"},
                "direction": "min",
                "budget": 10,
                "proposer": [sys.executable, str(FIXTURES / "proposer.py")],
                "evaluator": [sys.executable, str(FIXTURES / "evaluator.py")],
            }
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
            self.assertEqual(
                state["residuals"][-1]["program_id"], record["descendant_id"]
            )
            second = run_round(workspace)
            self.assertEqual(second["verdict"], "SUPPORTED")
            state = load(workspace / "state.json")
            self.assertEqual(state["round"], 2)
            self.assertEqual(state["spent"], 9)

    def test_recovery_keeps_the_charged_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "initial.py").write_text("def run(x):\n    return x\n")
            config = {
                "initial_program": "initial.py",
                "initial_residual": {
                    "id": "r0",
                    "question": "What produces the gain?",
                    "scope": "run",
                    "probe_input": 1,
                },
                "contract": {},
                "budget": 10,
                "proposer": [sys.executable, str(FIXTURES / "proposer.py")],
                "evaluator": [sys.executable, str(FIXTURES / "evaluator.py")],
            }
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

    def test_inconclusive_round_preserves_original_residual(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "initial.py").write_text("def run(x):\n    return x\n")
            proposer = root / "proposer.py"
            proposer.write_text(
                (FIXTURES / "proposer.py")
                .read_text()
                .replace('"targeted": "loss"', '"targeted": "other"')
            )
            config = {
                "initial_program": "initial.py",
                "initial_residual": {
                    "id": "r0",
                    "question": "What produces the gain?",
                    "scope": "run",
                    "probe_input": 1,
                },
                "contract": {},
                "budget": 10,
                "proposer": [sys.executable, str(proposer)],
                "evaluator": [sys.executable, str(FIXTURES / "evaluator.py")],
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            workspace = root / "run"
            initialize(workspace, config_path)
            record = run_round(workspace)
            state = load(workspace / "state.json")
            self.assertEqual(record["verdict"], "UNRESOLVED")
            self.assertTrue(record["retained_candidate"])
            self.assertEqual(state["residuals"][0]["status"], "OPEN")
            self.assertEqual(
                state["residuals"][-1]["program_id"], record["descendant_id"]
            )

    def test_unidentifiable_proposal_is_revised_before_evaluation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "initial.py").write_text("def run(x):\n    return x\n")
            proposer = root / "proposer.py"
            original = (FIXTURES / "proposer.py").read_text()
            injection = (
                '    if request["phase"] == "proposal" and "proposal_feedback" not in request["context"]:\n'
                '        for condition in response["conditions"]:\n'
                '            condition["predictions"]["alternative"] = condition["predictions"]["targeted"]\n'
            )
            proposer.write_text(
                original.replace(
                    "    json.dump(response, sys.stdout)",
                    injection + "    json.dump(response, sys.stdout)",
                )
            )
            config = {
                "initial_program": "initial.py",
                "initial_residual": {
                    "id": "r0",
                    "question": "What produces the gain?",
                    "scope": "run",
                    "probe_input": 1,
                },
                "contract": {},
                "budget": 10,
                "proposer": [sys.executable, str(proposer)],
                "evaluator": [sys.executable, str(FIXTURES / "evaluator.py")],
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            workspace = root / "run"
            initialize(workspace, config_path)
            record = run_round(workspace)
            state = load(workspace / "state.json")
            self.assertEqual(record["verdict"], "SUPPORTED")
            self.assertEqual(state["spent"], 5)


if __name__ == "__main__":
    unittest.main()
