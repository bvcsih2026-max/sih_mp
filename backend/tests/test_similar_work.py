"""
Tests for ml.detectors.similar_work.SimilarWorkDetector

Run with:
    python -m pytest tests/test_similar_work.py -v
or:
    python -m unittest tests.test_similar_work -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.detectors.similar_work import SimilarWorkDetector, SimilarWorkConfig


def make_work(work_id, description, work_type="Community Infrastructure",
              district="Alwar", location=(27.5530, 76.6346),
              sanction_amount=1000000, sanction_date="2024-01-15"):
    return {
        "work_id": work_id,
        "description": description,
        "work_type": work_type,
        "district": district,
        "location": location,
        "sanction_amount": sanction_amount,
        "sanction_date": sanction_date,
    }


class TestSimilarWorkDetector(unittest.TestCase):

    def setUp(self):
        self.detector = SimilarWorkDetector()

    def test_no_signals_for_fewer_than_two_works(self):
        self.assertEqual(self.detector.detect([]), [])
        self.assertEqual(self.detector.detect([make_work("W1", "Construction of road")]), [])

    def test_detects_highly_similar_pair(self):
        works = [
            make_work("WORK-001", "Construction of community hall at Village X",
                       location=(27.5530, 76.6346), sanction_amount=1000000,
                       sanction_date="2024-01-15"),
            make_work("WORK-002", "Construction of community hall near Village X",
                       location=(27.5600, 76.6400), sanction_amount=1050000,
                       sanction_date="2024-02-01"),
        ]
        signals = self.detector.detect(works)
        self.assertEqual(len(signals), 1)
        sig = signals[0]
        self.assertEqual(sig["detector_type"], "similar_work")
        self.assertEqual(sig["status"], "NEW")
        self.assertIn(sig["priority"], ("HIGH", "MEDIUM", "LOW"))
        self.assertGreater(sig["observed_evidence"]["text_similarity"], 0.5)
        self.assertTrue(sig["observed_evidence"]["same_district"])
        self.assertIn("location_distance_km", sig["observed_evidence"])
        self.assertIn("amount_difference_percent", sig["observed_evidence"])

    def test_no_signal_for_unrelated_works(self):
        works = [
            make_work("WORK-001", "Construction of community hall at Village X"),
            make_work("WORK-002", "Installation of solar street lights in Ward 7",
                       work_type="Solar Lighting", district="Bhilwara",
                       location=(25.3463, 74.6364), sanction_amount=300000,
                       sanction_date="2023-06-01"),
        ]
        signals = self.detector.detect(works)
        self.assertEqual(signals, [])

    def test_signal_schema_fields_present(self):
        works = [
            make_work("WORK-001", "Construction of drinking water tank at Village Y"),
            make_work("WORK-002", "Construction of drinking water tank at Village Y"),
        ]
        signals = self.detector.detect(works)
        self.assertEqual(len(signals), 1)
        required_keys = {
            "signal_id", "schema_version", "work_id", "detector_type",
            "priority", "anomaly_score", "title", "observed_evidence",
            "baseline", "explanation", "possible_explanation",
            "recommended_verification", "status", "source", "metadata",
        }
        self.assertTrue(required_keys.issubset(signals[0].keys()))
        self.assertIsInstance(signals[0]["possible_explanation"], list)
        self.assertIsInstance(signals[0]["recommended_verification"], list)
        self.assertGreater(len(signals[0]["possible_explanation"]), 0)

    def test_explanation_does_not_assert_wrongdoing(self):
        """The explanation may *mention* fraud/corruption only to explicitly
        disclaim them — it must never assert that fraud/corruption/illegal
        activity was found."""
        works = [
            make_work("WORK-001", "Construction of community hall at Village X"),
            make_work("WORK-002", "Construction of community hall near Village X"),
        ]
        signals = self.detector.detect(works)
        explanation = signals[0]["explanation"].lower()
        self.assertIn("not itself a finding of fraud", explanation)
        for banned_phrase in ("confirmed fraud", "is fraud", "illegal activity detected", "corruption confirmed"):
            self.assertNotIn(banned_phrase, explanation)
        # Also verify the possible_explanation list offers legitimate,
        # non-accusatory reasons rather than assuming wrongdoing.
        for phrase in signals[0]["possible_explanation"]:
            self.assertNotIn("fraud", phrase.lower())
            self.assertNotIn("corrupt", phrase.lower())

    def test_thresholds_are_configurable(self):
        works = [
            make_work("WORK-001", "Construction of community hall at Village X"),
            make_work("WORK-002", "Repair of primary school building in Village Z",
                       district="Kota", location=(25.2138, 75.8648),
                       sanction_amount=500000, sanction_date="2022-05-01"),
        ]
        loose_cfg = SimilarWorkConfig(text_similarity_threshold=0.0, combined_score_threshold=0.0)
        loose_detector = SimilarWorkDetector(config=loose_cfg)
        loose_signals = loose_detector.detect(works)

        strict_cfg = SimilarWorkConfig(text_similarity_threshold=0.9, combined_score_threshold=0.95)
        strict_detector = SimilarWorkDetector(config=strict_cfg)
        strict_signals = strict_detector.detect(works)

        self.assertGreaterEqual(len(loose_signals), len(strict_signals))

    def test_amount_and_date_evidence_only_added_when_comparable(self):
        work_a = make_work("WORK-001", "Construction of community hall at Village X")
        work_b = make_work("WORK-002", "Construction of community hall near Village X")
        work_b["sanction_amount"] = None
        work_b["sanction_date"] = None

        signals = self.detector.detect([work_a, work_b])
        self.assertEqual(len(signals), 1)
        evidence = signals[0]["observed_evidence"]
        self.assertNotIn("amount_difference_percent", evidence)
        self.assertNotIn("date_difference_days", evidence)

    def test_missing_optional_fields_do_not_crash(self):
        minimal_a = {"work_id": "WORK-001", "description": "Construction of a road in Ward 3"}
        minimal_b = {"work_id": "WORK-002", "description": "Construction of a road in Ward 3"}
        signals = self.detector.detect([minimal_a, minimal_b])
        self.assertEqual(len(signals), 1)

    def test_signals_sorted_descending_by_score(self):
        works = [
            make_work("WORK-001", "Construction of community hall at Village X"),
            make_work("WORK-002", "Construction of community hall near Village X"),
            make_work("WORK-003", "Construction of community centre at Village X area",
                       location=(28.0, 77.0), sanction_amount=2000000,
                       sanction_date="2025-09-01"),
        ]
        signals = self.detector.detect(works)
        scores = [s["anomaly_score"] for s in signals]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
