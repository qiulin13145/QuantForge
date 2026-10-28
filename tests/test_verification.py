import unittest

from quantforge.protocol import ContractError
from quantforge.runtime.verification import check_response


class VerificationTests(unittest.TestCase):
    def test_probe_rejects_noop_and_unreached_change(self):
        before = "def run(x):\n    return x + 1\n"
        with self.assertRaises(ContractError):
            check_response(before, before, "run", 1)
        before = "def run(x):\n    if x < 0:\n        return x\n    return x + 1\n"
        dead = "def run(x):\n    if x < 0:\n        return x + 2\n    return x + 1\n"
        with self.assertRaises(ContractError):
            check_response(before, dead, "run", 1)


if __name__ == "__main__":
    unittest.main()
