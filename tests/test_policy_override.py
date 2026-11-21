"""Tests for plan-policy-override (stdlib unittest only)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from policy_override import apply_overrides, validate_override, verdict

TODAY = date(2026, 11, 21)
PLAN = {"id": "summarise-paper", "version": 2}
MEDIUM = {"rule_id": "ORG-01", "severity": "MEDIUM", "step_id": "s2",
          "message": "Over budget."}
HIGH = {"rule_id": "SEC-01", "severity": "HIGH", "step_id": "s3",
        "message": "Ungated irreversible send."}
LOW = {"rule_id": "ETH-01", "severity": "LOW", "step_id": "s1",
       "message": "No reason recorded."}


def override(**changes):
    base = {"id": "OVR-1", "rule_id": "ORG-01", "step_id": "s2",
            "plan_id": "summarise-paper", "plan_version": 2,
            "reviewer": "akhila", "reason": "Budget is $2 for this run.",
            "expires": "2026-12-31"}
    base.update(changes)
    return base


class TestPolicyOverride(unittest.TestCase):
    def test_valid_override_waives_medium_finding(self):
        remaining, applied, rejected = apply_overrides(
            [MEDIUM, LOW], [override()], PLAN, TODAY)
        self.assertEqual(remaining, [LOW])
        self.assertEqual(len(applied), 1)
        self.assertEqual(rejected, [])
        self.assertEqual(verdict(remaining), "NEEDS REVIEW")

    def test_high_finding_cannot_be_overridden(self):
        remaining, applied, rejected = apply_overrides(
            [HIGH], [override(rule_id="SEC-01", step_id="s3")], PLAN, TODAY)
        self.assertEqual(remaining, [HIGH])
        self.assertEqual(applied, [])
        self.assertIn("HIGH", rejected[0]["reason"])

    def test_expired_override_is_rejected(self):
        remaining, applied, rejected = apply_overrides(
            [MEDIUM], [override(expires="2026-11-20")], PLAN, TODAY)
        self.assertEqual(remaining, [MEDIUM])
        self.assertEqual(applied, [])
        self.assertIn("expired", rejected[0]["reason"])

    def test_step_scoped_override_waives_only_that_step(self):
        other = dict(MEDIUM, step_id="s9")
        remaining, applied, _ = apply_overrides(
            [MEDIUM, other], [override()], PLAN, TODAY)
        self.assertEqual(remaining, [other])

    def test_override_for_wrong_plan_version_is_rejected(self):
        remaining, applied, rejected = apply_overrides(
            [MEDIUM], [override(plan_version=3)], PLAN, TODAY)
        self.assertEqual(remaining, [MEDIUM])
        self.assertIn("plan_version", rejected[0]["reason"])

    def test_short_reason_is_rejected(self):
        errors = validate_override(override(reason="ok"), PLAN, set(), TODAY)
        self.assertTrue(any("reason" in e for e in errors))

    def test_duplicate_override_id_is_rejected(self):
        remaining, applied, rejected = apply_overrides(
            [MEDIUM, LOW],
            [override(), override(id="OVR-1", rule_id="ETH-01", step_id="s1")],
            PLAN, TODAY)
        self.assertEqual(len(applied), 1)
        self.assertTrue(any("duplicate" in r["reason"] for r in rejected))

    def test_override_matching_no_finding_is_rejected(self):
        remaining, applied, rejected = apply_overrides(
            [MEDIUM], [override(rule_id="NOPE-99")], PLAN, TODAY)
        self.assertEqual(remaining, [MEDIUM])
        self.assertIn("no remaining finding", rejected[0]["reason"])

    def test_clean_verdict_when_all_findings_waived(self):
        remaining, applied, rejected = apply_overrides(
            [MEDIUM], [override()], PLAN, TODAY)
        self.assertEqual(remaining, [])
        self.assertEqual(verdict(remaining), "CLEAN")


if __name__ == "__main__":
    unittest.main()
