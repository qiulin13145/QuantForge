import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from quantforge.engine import initialize, run_round
from quantforge.storage import load


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "binpacking"

FIRST_FIT = '''def pack(items, capacity):
    bins = []
    for item in items:
        for bin_ in bins:
            if sum(bin_) + item <= capacity:
                bin_.append(item)
                break
        else:
            bins.append([item])
    return bins
'''

SORTED_FIRST_FIT = FIRST_FIT.replace("for item in items:", "for item in sorted(items, reverse=True):")


class BinPackingExampleTest(unittest.TestCase):
    def test_evaluator_checks_packing_and_compares_with_parent(self):
        config = json.loads((EXAMPLE / "config.json").read_text())
        baseline = (EXAMPLE / "baseline.py").read_text()
        request = {"source": FIRST_FIT, "parent_source": baseline, "condition": {"id": "primary"},
                   "contract": config["contract"], "phase": "evaluation"}
        result = subprocess.run([sys.executable, str(EXAMPLE / "evaluator.py")], input=json.dumps(request),
                                text=True, capture_output=True, check=True)
        output = json.loads(result.stdout)
        self.assertTrue(output["success"])
        self.assertEqual(output["outcome"], "gain")
        request["source"] = "def pack(items, capacity):\n    return [items]\n"
        result = subprocess.run([sys.executable, str(EXAMPLE / "evaluator.py")], input=json.dumps(request),
                                text=True, capture_output=True, check=True)
        self.assertFalse(json.loads(result.stdout)["safe"])

    def test_a_complete_search_round_with_a_custom_problem(self):
        baseline = (EXAMPLE / "baseline.py").read_text()
        proposal = {"source": FIRST_FIT,
                    "explanations": [{"id": "reuse", "claim": "reusing earlier bins reduces waste"},
                                     {"id": "other", "claim": "the gain remains without reusing earlier bins"}],
                    "conditions": [{"id": "primary", "kind": "primary", "cost": 1,
                                    "predictions": {"reuse": "gain", "other": "gain"}},
                                   {"id": "no-reuse", "kind": "control", "cost": 1,
                                    "source": baseline,
                                    "predictions": {"reuse": "unchanged", "other": "gain"}}]}
        response = {"source": SORTED_FIRST_FIT,
                    "next_residual": {"id": "ordering", "question": "How does item order affect packing?",
                                      "scope": "pack", "probe_input": {"args": [[4, 4, 6, 6], 10]}}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposer = root / "proposer.py"
            proposer.write_text("import json,sys\nrequest=json.load(sys.stdin)\n"
                                + "proposal=" + repr(proposal) + "\nresponse=" + repr(response) + "\n"
                                + "json.dump(proposal if request['phase']=='proposal' else response,sys.stdout)\n")
            config = json.loads((EXAMPLE / "config.json").read_text())
            config["initial_program"] = str(EXAMPLE / "baseline.py")
            config["proposer"] = [sys.executable, str(proposer)]
            config["evaluator"] = [sys.executable, str(EXAMPLE / "evaluator.py")]
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            workspace = root / "run"
            initialize(workspace, config_path)
            record = run_round(workspace)
            state = load(workspace / "state.json")
            self.assertEqual(record["verdict"], "SUPPORTED")
            self.assertTrue(record["probe_evaluation"]["response_valid"])
            self.assertEqual(state["round"], 1)
            self.assertEqual(state["residuals"][-1]["id"], "ordering")

    def test_cli_and_codex_adapter_complete_a_custom_round(self):
        baseline = (EXAMPLE / "baseline.py").read_text()
        proposal = {"source": FIRST_FIT,
                    "explanations": [{"id": "reuse", "claim": "reusing bins reduces waste"},
                                     {"id": "other", "claim": "gain persists without reusing bins"}],
                    "conditions": [{"id": "primary", "kind": "primary", "cost": 1,
                                    "predictions": {"reuse": "gain", "other": "gain"}},
                                   {"id": "no-reuse", "kind": "control", "cost": 1, "source": baseline,
                                    "predictions": {"reuse": "unchanged", "other": "gain"}}]}
        response = {"source": SORTED_FIRST_FIT,
                    "next_residual": {"id": "ordering", "question": "How does item order affect packing?",
                                      "scope": "pack", "probe_input": {"args": [[4, 4, 6, 6], 10]}}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex = root / "codex"
            codex.write_text("#!" + sys.executable + "\nimport json,sys\n"
                             "assert 'bin packing' in sys.stdin.read().lower()\n"
                             "schema=json.load(open(sys.argv[sys.argv.index('--output-schema')+1]))\n"
                             + "proposal=" + repr(proposal) + "\nresponse=" + repr(response) + "\n"
                             + "output=sys.argv[sys.argv.index('--output-last-message')+1]\n"
                               "json.dump(response if 'next_residual' in schema['properties'] else proposal,open(output,'w'))\n")
            codex.chmod(0o755)
            task = root / "my-task"
            shutil.copytree(EXAMPLE, task, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            config_path = task / "config.json"
            config = json.loads(config_path.read_text())
            config["proposer"] = [sys.executable, "-m", "quantforge.backends.codex", "--command", str(codex)]
            config["evaluator"] = [sys.executable, "{config_dir}/evaluator.py"]
            config_path.write_text(json.dumps(config))
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
            workspace = root / "run"
            for args in (["init", str(workspace), "--config", str(config_path)], ["step", str(workspace)], ["status", str(workspace)]):
                result = subprocess.run([sys.executable, "-m", "quantforge.cli", *args], cwd=root,
                                        env=env, text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout)["round"], 1)
            state = load(workspace / "state.json")
            self.assertEqual(state["history"][0]["verdict"], "SUPPORTED")
            self.assertTrue(state["history"][0]["probe_evaluation"]["response_valid"])


if __name__ == "__main__":
    unittest.main()
