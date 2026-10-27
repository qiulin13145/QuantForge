import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ADAPTER = Path(__file__).resolve().parents[1] / "src/quantforge/backends/codex.py"
REQUEST = {"prompt": "Return JSON", "json_schema": {"type": "object"}}


class ProposerCommandTests(unittest.TestCase):
    def invoke(self, fake, request=REQUEST):
        return subprocess.run([sys.executable, str(ADAPTER), "--command", str(fake)],
            input=json.dumps(request), text=True, capture_output=True, check=False, timeout=10)

    def test_stdout_is_one_json_object(self):
        with tempfile.TemporaryDirectory() as root:
            fake = Path(root) / "fake-codex"
            fake.write_text("#!/usr/bin/env python3\n"
                "import sys,json\n"
                "assert 'Return JSON' in sys.stdin.read()\n"
                "path=sys.argv[sys.argv.index('--output-last-message')+1]\n"
                "open(path,'w').write(json.dumps({'source':'def f(): return 1'}))\n"
                "print('this progress must not appear on stdout')\n")
            fake.chmod(0o755)
            run = self.invoke(fake)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), {"source": "def f(): return 1"})
            self.assertEqual(run.stderr, "")

    def test_failure_is_nonzero_and_does_not_leak_cli_output(self):
        with tempfile.TemporaryDirectory() as root:
            fake = Path(root) / "fake-codex"
            fake.write_text("#!/usr/bin/env python3\nimport sys\nprint('secret', file=sys.stderr)\nsys.exit(2)\n")
            fake.chmod(0o755)
            run = self.invoke(fake)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(run.stdout, "")
            self.assertNotIn("secret", run.stderr)

    def test_rejects_malformed_request(self):
        run = self.invoke("unused", {"prompt": "missing schema"})
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(run.stdout, "")
        self.assertIn("json_schema", run.stderr)


if __name__ == "__main__":
    unittest.main()
