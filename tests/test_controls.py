import unittest

from quantforge.protocol import ContractError
from quantforge.search.controls import validate_and_select
from _support import proposal


class ControlTests(unittest.TestCase):
    def test_minimum_cost_and_unidentifiable_proposals(self):
        p = proposal()
        self.assertEqual(
            [c["id"] for c in validate_and_select(p)], ["primary", "cheap"]
        )
        for c in p["conditions"]:
            c["predictions"] = {"f": "same", "c": "same"}
        with self.assertRaises(ContractError):
            validate_and_select(p)


if __name__ == "__main__":
    unittest.main()
