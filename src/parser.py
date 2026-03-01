"""
Resume & JD Parser — converts raw text/PDF into structured ParsedResume / ParsedJD.
Uses Groq (free) with llama-3.3-70b-versatile for LLM extraction.
"""

from pathlib import Path
from typing import Union

from .groq_client import chat_json
from .models import ParsedResume, ParsedJD


RESUME_PROMPT = """Extract structured information from this resume and return ONLY a JSON object.

JSON schema (follow exactly):
{
  "name": "full name",
  "email": "email or empty string",
  "phone": "phone or empty string",
  "summary": "2-3 sentence professional summary",
  "skills": ["skill1", "skill2"],
  "experience": [
    {
      "title": "job title",
      "company": "company name",
      "duration_months": 12,
      "description": "role description",
      "achievements": ["quantified result 1", "quantified result 2"]
    }
  ],
  "education": [
    {
      "degree": "degree name",
      "institution": "school name",
      "year": "graduation year"
    }
  ],
  "github_url": "url or null",
  "linkedin_url": "url or null",
  "certifications": ["cert1"],
  "years_of_experience": 5.0
}

Rules:
- skills: ALL technical skills, tools, languages, frameworks found
- achievements: ONLY quantified results (%, $, counts, scale); skip vague statements
- duration_months: calculate from dates; use 12 if unknown
- years_of_experience: total professional work years

Resume:
"""

JD_PROMPT = """Extract structured information from this job description. Return ONLY JSON.

JSON schema:
{
  "title": "job title",
  "company": "company name or Unknown",
  "required_skills": ["skill1"],
  "preferred_skills": ["skill1"],
  "responsibilities": ["top 5 duties"],
  "min_years_experience": 3.0,
  "education_requirement": "Bachelor's in CS or equivalent",
  "description": "2-3 sentence role summary"
}

Rules:
- required_skills: explicit "must have" / "required" items
- preferred_skills: "nice to have" / "preferred" items
- min_years_experience: minimum number stated; 0 if not mentioned

Job Description:
"""


class ResumeParser:
    """Parses resumes and JDs using Groq's free LLM API."""

    def parse_resume(self, text: str) -> ParsedResume:
        data = chat_json(RESUME_PROMPT + text)
        return ParsedResume(
            name=data.get("name", "Unknown"),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            summary=data.get("summary", ""),
            skills=[s.strip() for s in data.get("skills", [])],
            experience=data.get("experience", []),
            education=data.get("education", []),
            github_url=data.get("github_url") or None,
            linkedin_url=data.get("linkedin_url") or None,
            certifications=data.get("certifications", []),
            years_of_experience=float(data.get("years_of_experience", 0)),
            raw_text=text,
        )

    def parse_resume_from_file(self, path: Union[str, Path]) -> ParsedResume:
        text = self._read_file(path)
        return self.parse_resume(text)

    def parse_jd(self, text: str) -> ParsedJD:
        data = chat_json(JD_PROMPT + text)
        return ParsedJD(
            title=data.get("title", "Unknown"),
            company=data.get("company", "Unknown"),
            required_skills=[s.strip() for s in data.get("required_skills", [])],
            preferred_skills=[s.strip() for s in data.get("preferred_skills", [])],
            responsibilities=data.get("responsibilities", []),
            min_years_experience=float(data.get("min_years_experience", 0)),
            education_requirement=data.get("education_requirement", ""),
            description=data.get("description", ""),
        )

    def _read_file(self, path: Union[str, Path]) -> str:
        path = Path(path)
        if path.suffix.lower() == ".txt":
            return path.read_text(encoding="utf-8")
        elif path.suffix.lower() == ".pdf":
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(str(path))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                raise RuntimeError("Install PyPDF2: pip install PyPDF2")
        else:
            raise ValueError(f"Unsupported file type: {path.suffix}")
