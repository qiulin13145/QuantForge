import unittest

from quantforge.search.controls import validate_and_select
from quantforge.search.verdicts import verdict
from _support import proposal


class VerdictTests(unittest.TestCase):
    def test_unsafe_control_and_missing_signature(self):
        p = proposal()
        selected = validate_and_select(p)
        results = {
            "primary": {
                "safe": True,
                "success": True,
                "score": 1,
                "signature": True,
                "outcome": "gain",
            },
            "cheap": {
                "safe": False,
                "success": True,
                "score": 2,
                "signature": False,
                "outcome": "loss",
            },
        }
        self.assertEqual(verdict(p, selected, results, 2)[0], "UNSAFE")
        results["cheap"]["safe"] = True
        results["primary"]["signature"] = False
        self.assertEqual(verdict(p, selected, results, 2)[0], "TARGET_ONLY")

    def test_inconclusive_evidence_does_not_discard_gain_or_imply_no_effect(self):
        p = proposal()
        selected = validate_and_select(p)
        results = {
            "primary": {
                "safe": True,
                "success": True,
                "score": 1,
                "signature": True,
                "outcome": "gain",
            },
            "cheap": {
                "safe": True,
                "success": True,
                "score": 2,
                "signature": False,
                "outcome": "gain",
            },
        }
        self.assertEqual(verdict(p, selected, results, 2), ("UNRESOLVED", True))
        results["primary"].update(score=3, signature=False, outcome="loss")
        self.assertEqual(verdict(p, selected, results, 2), ("UNRESOLVED", False))
        results["primary"]["score"] = 2
        results["primary"]["parent_equivalent"] = True
        self.assertEqual(verdict(p, selected, results, 2), ("NO_EFFECT", False))


if __name__ == "__main__":
    unittest.main()
