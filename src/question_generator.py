"""
Intelligent Tiering & Question Generator
==========================================
Uses Groq (free, llama-3.3-70b) to generate tailored interview questions
calibrated to the candidate's tier, skill gaps, and unique background.
"""

import json
import re
from typing import Optional

from .groq_client import chat_json
from .models import (
    ParsedResume, ParsedJD, ScoreBreakdown, Tier,
    InterviewQuestion, CandidateEvaluation, VerificationResult,
)
from .scoring import ScoringEngine


TIER_CONFIG = {
    Tier.A: dict(num=8, tech=4, behavioral=2, situational=2,
                 desc="Fast-track — probe seniority depth and leadership breadth"),
    Tier.B: dict(num=7, tech=3, behavioral=2, situational=2,
                 desc="Technical Screen — validate core skills and growth mindset"),
    Tier.C: dict(num=6, tech=3, behavioral=2, situational=1,
                 desc="Needs Evaluation — test fundamentals and potential"),
}

QUESTION_PROMPT = """You are a senior technical interviewer. Generate highly targeted interview questions for this specific candidate.

=== JOB ===
Title: {job_title}
Required skills: {required_skills}

=== CANDIDATE ===
Name: {name} | Experience: {years_exp} years
Skills: {skills}
Roles: {roles}
Key achievements: {achievements}
Tier: {tier} — {tier_desc}

=== SCORE GAPS (use to probe weaknesses) ===
Exact Match {exact}/100: {exact_reason}
Semantic {semantic}/100: {semantic_reason}
Achievements {achieve}/100: {achieve_reason}
Ownership {own}/100: {own_reason}

=== TASK ===
Generate exactly {num} interview questions:
- {tech} technical deep-dive questions (probe real understanding, not surface recall)
- {behavioral} behavioral questions (STAR format; probe ownership and impact claims)
- {situational} situational/system design questions (calibrated to Tier {tier})

Rules:
1. Questions must reference this candidate's SPECIFIC background, not be generic
2. Target score gaps — if Kafka is required but not on resume, include a Kafka/streaming question
3. Tier A → advanced questions testing seniority; Tier C → foundational with clear bar
4. Include an expected-answer hint so the interviewer knows what good looks like

Return ONLY a JSON array (no markdown, no explanation):
[
  {{
    "question": "full question text",
    "category": "technical|behavioral|situational",
    "difficulty": "easy|medium|hard",
    "rationale": "why this question for this specific candidate",
    "expected_answer_hints": "what a strong answer looks like"
  }}
]"""


class QuestionGenerator:

    def generate(
        self,
        resume: ParsedResume,
        jd: ParsedJD,
        scores: ScoreBreakdown,
        tier: Tier,
    ) -> list[InterviewQuestion]:
        cfg = TIER_CONFIG[tier]

        roles = [
            f"{e.get('title','')} @ {e.get('company','')} "
            f"({e.get('duration_months', 0) // 12}yr)"
            for e in resume.experience[:4]
        ]
        achievements = [
            a for exp in resume.experience[:3]
            for a in exp.get("achievements", [])[:2]
        ]

        prompt = QUESTION_PROMPT.format(
            job_title=jd.title,
            required_skills=", ".join(jd.required_skills[:14]),
            name=resume.name,
            years_exp=resume.years_of_experience,
            skills=", ".join(resume.skills[:25]),
            roles="; ".join(roles) or "No prior experience listed",
            achievements="; ".join(achievements[:5]) or "No quantified achievements found",
            tier=tier.value,
            tier_desc=cfg["desc"],
            exact=scores.exact_match,
            exact_reason=scores.exact_match_reason[:130],
            semantic=scores.semantic_similarity,
            semantic_reason=scores.semantic_similarity_reason[:130],
            achieve=scores.achievement_impact,
            achieve_reason=scores.achievement_impact_reason[:130],
            own=scores.ownership_leadership,
            own_reason=scores.ownership_leadership_reason[:130],
            num=cfg["num"],
            tech=cfg["tech"],
            behavioral=cfg["behavioral"],
            situational=cfg["situational"],
        )

        try:
            items = chat_json(prompt, max_tokens=3500)
            if not isinstance(items, list):
                raise ValueError("Expected JSON array")
        except Exception:
            return self._fallback(tier)

        return [
            InterviewQuestion(
                question=q.get("question", ""),
                category=q.get("category", "technical"),
                difficulty=q.get("difficulty", "medium"),
                rationale=q.get("rationale", ""),
                expected_answer_hints=q.get("expected_answer_hints", ""),
            )
            for q in items if q.get("question")
        ]

    def _fallback(self, tier: Tier) -> list[InterviewQuestion]:
        return [
            InterviewQuestion(
                question="Walk me through the most technically complex system you've designed end-to-end.",
                category="technical", difficulty="medium",
                rationale="Assesses depth of system design thinking.",
                expected_answer_hints="Architecture clarity, trade-off awareness, scalability, failure handling.",
            ),
            InterviewQuestion(
                question="Tell me about a time you owned a project fully. What was the outcome and what would you do differently?",
                category="behavioral", difficulty="medium",
                rationale="Assesses ownership, accountability, and self-reflection.",
                expected_answer_hints="STAR format, clear impact stated, honest reflection on gaps.",
            ),
        ]


class TieringEngine:
    """Combines scoring + question generation into a complete evaluation."""

    def __init__(self, use_llm_augmentation: bool = True):
        self.scorer = ScoringEngine(use_llm_augmentation=use_llm_augmentation)
        self.question_gen = QuestionGenerator()

    def evaluate(
        self,
        resume: ParsedResume,
        jd: ParsedJD,
        verification: Optional[VerificationResult] = None,
    ) -> CandidateEvaluation:
        scores = self.scorer.score(resume, jd)
        tier, tier_reason = self.scorer.classify_tier(scores, resume, jd)
        questions = self.question_gen.generate(resume, jd, scores, tier)

        green, red = [], []

        if scores.achievement_impact >= 70:
            green.append("Strong quantified achievements")
        if scores.exact_match >= 80:
            green.append("Excellent skill alignment")
        if resume.years_of_experience >= jd.min_years_experience:
            green.append(f"Meets experience requirement ({resume.years_of_experience:.1f}yr)")
        if scores.ownership_leadership >= 60:
            green.append("Clear ownership and leadership signals")
        if verification and verification.github_authenticity_score >= 70:
            green.append("Active GitHub profile validates technical claims")

        if scores.achievement_impact < 40:
            red.append("Lacks quantified achievements — impact hard to assess")
        if scores.exact_match < 40:
            red.append(f"Significant skill gap (exact match: {scores.exact_match:.0f}/100)")
        if resume.years_of_experience < jd.min_years_experience * 0.7:
            red.append(
                f"Under-experienced ({resume.years_of_experience:.1f}yr vs "
                f"{jd.min_years_experience}yr required)"
            )
        if verification:
            red.extend(verification.flags)

        tier_actions = {
            Tier.A: "→ Proceed directly to hiring manager interview.",
            Tier.B: "→ Schedule 45-min technical screen with team lead.",
            Tier.C: "→ Hold for further review or consider junior variant of role.",
        }
        recommendation = (
            f"**{resume.name}** | Composite: {scores.composite_score:.1f}/100 | "
            f"Tier {tier.value}  {tier_actions[tier]}\n"
            + (f"✅ {'; '.join(green[:3])}\n" if green else "")
            + (f"⚠️  {'; '.join(red[:3])}" if red else "")
        )

        return CandidateEvaluation(
            candidate_name=resume.name,
            job_title=jd.title,
            resume=resume,
            jd=jd,
            scores=scores,
            tier=tier,
            tier_reason=tier_reason,
            verification=verification,
            interview_questions=questions,
            overall_recommendation=recommendation,
            green_flags=green,
            red_flags=red,
        )
