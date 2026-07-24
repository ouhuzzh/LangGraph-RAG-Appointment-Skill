import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from rag_agent import clinical_safety  # noqa: E402
from rag_agent.node_helpers import _infer_risk_level  # noqa: E402


class ClassifySeverityTests(unittest.TestCase):
    def test_single_critical_symptom(self):
        self.assertEqual(clinical_safety.classify_severity("我突然胸痛"), "critical")

    def test_critical_combination(self):
        # Neither token alone is a hard red flag, but together they escalate.
        self.assertEqual(clinical_safety.classify_severity("突然剧烈头痛"), "critical")

    def test_high_symptom(self):
        self.assertEqual(clinical_safety.classify_severity("这两天剧烈腹痛"), "high")

    def test_moderate_dose_question(self):
        self.assertEqual(clinical_safety.classify_severity("这个药一次吃几片"), "moderate")

    def test_normal_query(self):
        self.assertEqual(clinical_safety.classify_severity("高血压平时饮食注意什么"), "normal")

    def test_empty_query(self):
        self.assertEqual(clinical_safety.classify_severity(""), "normal")


class SeverityOrderingTests(unittest.TestCase):
    def test_is_at_least(self):
        self.assertTrue(clinical_safety.is_at_least("critical", "high"))
        self.assertTrue(clinical_safety.is_at_least("high", "high"))
        self.assertFalse(clinical_safety.is_at_least("moderate", "high"))


class PrescriptionOverreachTests(unittest.TestCase):
    def test_detects_specific_dosing(self):
        self.assertTrue(clinical_safety.detect_prescription_overreach("每天3次，每次500mg"))
        self.assertTrue(clinical_safety.detect_prescription_overreach("建议服用2片"))

    def test_ignores_general_advice(self):
        self.assertFalse(clinical_safety.detect_prescription_overreach("多喝水、注意休息，必要时就医。"))


class EmergencyMessageTests(unittest.TestCase):
    def test_critical_and_high_render(self):
        self.assertIn("120", clinical_safety.emergency_escalation_message("critical"))
        self.assertIn("尽快线下就医", clinical_safety.emergency_escalation_message("high"))

    def test_normal_is_empty(self):
        self.assertEqual(clinical_safety.emergency_escalation_message("normal"), "")


class RiskInferenceIntegrationTests(unittest.TestCase):
    """_infer_risk_level must only consult the guardrail when the flag is on,
    and remain a strict superset (can raise risk, never lower it)."""

    def _set_flag(self, value):
        original = getattr(config, "ENABLE_CLINICAL_SAFETY_GUARDRAIL", False)
        config.ENABLE_CLINICAL_SAFETY_GUARDRAIL = value
        self.addCleanup(setattr, config, "ENABLE_CLINICAL_SAFETY_GUARDRAIL", original)

    def test_disabled_by_default_leaves_expanded_symptom_normal(self):
        self._set_flag(False)
        # "剧烈头痛" is not in the legacy HIGH_RISK_KEYWORDS list.
        self.assertEqual(_infer_risk_level("突然剧烈头痛"), "normal")

    def test_enabled_flags_expanded_symptom_high(self):
        self._set_flag(True)
        self.assertEqual(_infer_risk_level("突然剧烈头痛"), "high")

    def test_legacy_keyword_still_high_regardless_of_flag(self):
        self._set_flag(False)
        self.assertEqual(_infer_risk_level("我现在胸痛"), "high")


if __name__ == "__main__":
    unittest.main()
