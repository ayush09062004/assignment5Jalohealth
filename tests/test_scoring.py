"""
Unit tests — run with: pytest tests/ -v
Or without pytest: python tests/test_scoring.py
"""

import sys
import os
import unittest
import types
from unittest.mock import MagicMock

# Stub out network dependencies BEFORE importing any project modules
for mod_name in ["groq", "httpx"]:
    mock_mod = MagicMock()
    sys.modules[mod_name] = mock_mod

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import ParsedResume, ParsedJD, Tier
from src.scoring import (
    _compute_exact_match,
    _compute_semantic_similarity,
    _compute_achievement_impact,
    _compute_ownership_leadership,
    ScoringEngine,
)


def make_kafka_jd() -> ParsedJD:
    return ParsedJD(
        title="Backend Engineer", company="StreamCorp",
        required_skills=["Kafka", "Kubernetes", "Python", "PostgreSQL"],
        preferred_skills=["AWS", "Terraform", "Prometheus"],
        responsibilities=["Build streaming pipelines"],
        min_years_experience=4.0,
        education_requirement="BS CS",
        description="Build Kafka-based streaming systems.",
    )


def make_strong_resume() -> ParsedResume:
    return ParsedResume(
        name="Alex Chen", email="alex@test.com", phone="",
        summary="Senior SWE 6 years distributed systems.",
        skills=["Python", "Go", "Kubernetes", "AWS Kinesis", "RabbitMQ",
                "PostgreSQL", "Redis", "Terraform", "Prometheus"],
        experience=[{
            "title": "Senior SWE", "company": "DataCorp", "duration_months": 36,
            "description": (
                "Architected real-time pipeline using AWS Kinesis handling 2M events/day. "
                "Led migration reducing deployment by 70%."
            ),
            "achievements": [
                "Saved $180K/year in cloud costs",
                "Improved uptime to 99.97%",
                "Mentored team of 4 engineers; 2 promoted within 18 months",
            ],
        }],
        education=[],
        github_url="https://github.com/alexchen",
        years_of_experience=6.0,
    )


def make_weak_resume() -> ParsedResume:
    return ParsedResume(
        name="Bob Smith", email="", phone="", summary="",
        skills=["Excel", "PowerPoint", "Basic Python"],
        experience=[{
            "title": "Support Analyst", "company": "Corp", "duration_months": 12,
            "description": "Handled customer tickets and wrote documentation.",
            "achievements": [],
        }],
        education=[],
        years_of_experience=1.0,
    )


class TestExactMatch(unittest.TestCase):
    def test_strong_candidate_high_score(self):
        s, r = _compute_exact_match(make_strong_resume(), make_kafka_jd())
        self.assertGreaterEqual(s, 60, f"Expected ≥60, got {s}. Reason: {r}")

    def test_weak_candidate_low_score(self):
        s, _ = _compute_exact_match(make_weak_resume(), make_kafka_jd())
        self.assertLessEqual(s, 30, f"Expected ≤30, got {s}")

    def test_reason_mentions_missing_skills(self):
        _, r = _compute_exact_match(make_weak_resume(), make_kafka_jd())
        self.assertIn("Missing", r)


class TestSemanticSimilarity(unittest.TestCase):
    def test_kinesis_counts_for_kafka_role(self):
        """KEY TEST: Kinesis experience must score ≥50 for Kafka requirement."""
        s, r = _compute_semantic_similarity(make_strong_resume(), make_kafka_jd(), use_llm=False)
        self.assertGreaterEqual(s, 50,
            f"AWS Kinesis should count toward Kafka role. Got {s}. Reason: {r}")

    def test_rabbitmq_counts_for_kafka_role(self):
        resume = ParsedResume(
            name="T", email="", phone="", summary="",
            skills=["RabbitMQ", "Python", "PostgreSQL", "Docker"],
            experience=[], education=[], years_of_experience=4.0,
        )
        s, _ = _compute_semantic_similarity(resume, make_kafka_jd(), use_llm=False)
        self.assertGreaterEqual(s, 45, f"RabbitMQ→Kafka: expected ≥45, got {s}")

    def test_unrelated_skills_low_score(self):
        resume = ParsedResume(
            name="T", email="", phone="", summary="",
            skills=["Photoshop", "Illustrator", "SEO", "Marketing"],
            experience=[], education=[], years_of_experience=0.0,
        )
        s, _ = _compute_semantic_similarity(resume, make_kafka_jd(), use_llm=False)
        self.assertLessEqual(s, 30, f"Unrelated skills: expected ≤30, got {s}")


class TestAchievementImpact(unittest.TestCase):
    def test_quantified_achievements_score_high(self):
        s, r = _compute_achievement_impact(make_strong_resume())
        self.assertGreaterEqual(s, 60, f"Expected ≥60, got {s}")

    def test_no_achievements_score_low(self):
        s, _ = _compute_achievement_impact(make_weak_resume())
        self.assertLessEqual(s, 30, f"Expected ≤30, got {s}")

    def test_reason_mentions_count(self):
        _, r = _compute_achievement_impact(make_strong_resume())
        self.assertIn("quantified", r.lower())


class TestOwnershipLeadership(unittest.TestCase):
    def test_leadership_signals_detected(self):
        s, r = _compute_ownership_leadership(make_strong_resume())
        self.assertGreaterEqual(s, 50, f"Expected ≥50, got {s}. Reason: {r}")

    def test_no_leadership_signals_low(self):
        s, _ = _compute_ownership_leadership(make_weak_resume())
        self.assertLessEqual(s, 30, f"Expected ≤30, got {s}")


class TestTierClassification(unittest.TestCase):
    def setUp(self):
        self.engine = ScoringEngine(use_llm_augmentation=False)
        self.jd = make_kafka_jd()

    def test_strong_candidate_tier_a_or_b(self):
        sc = self.engine.score(make_strong_resume(), self.jd)
        tier, _ = self.engine.classify_tier(sc, make_strong_resume(), self.jd)
        self.assertIn(tier, {Tier.A, Tier.B}, f"Strong candidate should be A or B, got {tier}")

    def test_weak_candidate_tier_c(self):
        sc = self.engine.score(make_weak_resume(), self.jd)
        tier, _ = self.engine.classify_tier(sc, make_weak_resume(), self.jd)
        self.assertEqual(tier, Tier.C, f"Weak candidate should be C, got {tier}")

    def test_composite_in_valid_range(self):
        sc = self.engine.score(make_strong_resume(), self.jd)
        self.assertGreaterEqual(sc.composite_score, 0)
        self.assertLessEqual(sc.composite_score, 100)

    def test_all_scores_in_valid_range(self):
        sc = self.engine.score(make_strong_resume(), self.jd)
        for val in [sc.exact_match, sc.semantic_similarity,
                    sc.achievement_impact, sc.ownership_leadership]:
            self.assertGreaterEqual(val, 0)
            self.assertLessEqual(val, 100)


if __name__ == "__main__":
    # Run without pytest
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [TestExactMatch, TestSemanticSimilarity,
                TestAchievementImpact, TestOwnershipLeadership,
                TestTierClassification]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
