import math
import unittest

from eth_hai_clean.core import (
    TASK_ORDERS,
    calculate_reliance_metrics,
    condition_label,
    questionnaire_score,
    validate_task_orders,
)


class CleanCoreTests(unittest.TestCase):
    def test_task_orders(self):
        validate_task_orders()
        self.assertEqual(len(TASK_ORDERS), 10)

    def test_condition_mapping(self):
        self.assertEqual(condition_label(1, 0), "no tutorial, no xai")
        self.assertEqual(condition_label(0, 0), "with tutorial, no xai")
        self.assertEqual(condition_label(1, 1), "no tutorial, with xai")
        self.assertEqual(condition_label(0, 1), "with tutorial, with xai")

    def test_questionnaire_reverse_code(self):
        self.assertAlmostEqual(questionnaire_score([0, 1, 2], (1,), 5, True), (5 + 2 + 3) / 3)

    def test_canonical_reliance_metrics(self):
        # Cases: positive AI reliance, negative self reliance, positive self reliance,
        # negative AI reliance, correct agreement, correct third option, insist while
        # both are wrong, and leave an initially correct agreement.
        correct_ai_final = [
            ("A", "A", "B", "A"),
            ("A", "A", "B", "B"),
            ("A", "B", "A", "A"),
            ("A", "B", "A", "B"),
            ("A", "A", "A", "A"),
            ("A", "B", "C", "A"),
            ("A", "B", "C", "C"),
            ("A", "A", "A", "B"),
        ]
        row = {}
        task_answers = {}
        for i, (correct, ai, initial, final) in enumerate(correct_ai_final):
            task_answers[i] = (correct, ai)
            row["question%d" % i] = initial
            row["advice%d" % i] = final

        result = calculate_reliance_metrics(row, list(range(8)), task_answers, "zero")
        self.assertEqual(result.correct_count, 4)
        self.assertAlmostEqual(result.accuracy, 0.5)
        self.assertAlmostEqual(result.agreement_fraction, 3 / 8)
        self.assertEqual(result.initial_disagreement, 6)
        self.assertAlmostEqual(result.switch_fraction, 2 / 6)
        self.assertAlmostEqual(result.appropriate_reliance, 3 / 6)
        self.assertEqual(result.positive_ai_reliance, 1)
        self.assertEqual(result.negative_self_reliance, 1)
        self.assertEqual(result.positive_self_reliance, 1)
        self.assertEqual(result.negative_ai_reliance, 1)
        self.assertAlmostEqual(result.rair, 0.5)
        self.assertAlmostEqual(result.rsr, 0.5)

    def test_zero_denominator_policy(self):
        row = {"question0": "A", "advice0": "A"}
        task_answers = {0: ("A", "A")}
        zero = calculate_reliance_metrics(row, [0], task_answers, "zero")
        nan = calculate_reliance_metrics(row, [0], task_answers, "nan")
        self.assertEqual(zero.rair, 0.0)
        self.assertEqual(zero.rsr, 0.0)
        self.assertIsNone(nan.rair)
        self.assertIsNone(nan.rsr)

    def test_third_option_counts_as_appropriate_reliance(self):
        row = {"question0": "C", "advice0": "A"}
        task_answers = {0: ("A", "B")}
        result = calculate_reliance_metrics(row, [0], task_answers, "zero")
        self.assertEqual(result.initial_disagreement, 1)
        self.assertEqual(result.appropriate_reliance, 1.0)
        self.assertEqual(result.switch_fraction, 0.0)
        self.assertEqual(result.rair, 0.0)
        self.assertEqual(result.rsr, 0.0)


if __name__ == "__main__":
    unittest.main()
