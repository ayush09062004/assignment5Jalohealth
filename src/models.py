"""
Core data models for the AI Resume Shortlisting & Interview Assistant.
Zero external AI dependencies — all structures are plain Python dataclasses.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Tier(str, Enum):
    A = "A"   # Fast-track to hiring manager
    B = "B"   # Technical screen needed
    C = "C"   # Needs evaluation / junior


@dataclass
class ParsedResume:
    name: str
    email: str
    phone: str
    summary: str
    skills: list[str]
    experience: list[dict]      # [{title, company, duration_months, description, achievements[]}]
    education: list[dict]       # [{degree, institution, year}]
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    certifications: list[str] = field(default_factory=list)
    years_of_experience: float = 0.0
    raw_text: str = ""


@dataclass
class ParsedJD:
    title: str
    company: str
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    min_years_experience: float
    education_requirement: str
    description: str


@dataclass
class ScoreBreakdown:
    exact_match: float           # 0–100
    semantic_similarity: float   # 0–100
    achievement_impact: float    # 0–100
    ownership_leadership: float  # 0–100

    exact_match_reason: str = ""
    semantic_similarity_reason: str = ""
    achievement_impact_reason: str = ""
    ownership_leadership_reason: str = ""

    @property
    def composite_score(self) -> float:
        return round(
            self.exact_match * 0.30 +
            self.semantic_similarity * 0.30 +
            self.achievement_impact * 0.25 +
            self.ownership_leadership * 0.15,
            1
        )


@dataclass
class VerificationResult:
    github_active: Optional[bool] = None
    github_repos_count: Optional[int] = None
    github_recent_commits: Optional[int] = None
    github_languages: list[str] = field(default_factory=list)
    github_authenticity_score: float = 0.0
    github_notes: str = ""

    linkedin_reachable: Optional[bool] = None
    linkedin_notes: str = ""

    overall_credibility: float = 0.0
    flags: list[str] = field(default_factory=list)


@dataclass
class InterviewQuestion:
    question: str
    category: str       # technical | behavioral | situational
    difficulty: str     # easy | medium | hard
    rationale: str
    expected_answer_hints: str


@dataclass
class CandidateEvaluation:
    candidate_name: str
    job_title: str
    resume: ParsedResume
    jd: ParsedJD
    scores: ScoreBreakdown
    tier: Tier
    tier_reason: str
    verification: Optional[VerificationResult] = None
    interview_questions: list[InterviewQuestion] = field(default_factory=list)
    overall_recommendation: str = ""
    red_flags: list[str] = field(default_factory=list)
    green_flags: list[str] = field(default_factory=list)
