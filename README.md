# assignment5Jalohealth
Repo for Assignment 5 by Ayush Raj(IIT BHU)
Live at: https://assignment5jalohealth.streamlit.app/ 

# AI Resume Shortlisting & Interview Assistant
### Free Edition — powered by Groq (free API) + Llama 3.3 70B

**100% free to run.** No paid API keys required.
Uses [Groq's free tier](https://console.groq.com) — no credit card, generous limits (14,400 req/day).

---

## Features

| Feature | Status |
|---------|--------|
| Resume & JD parsing (LLM) | ✅ via Groq + Llama 3.3 70B |
| 4-dimensional scoring with explanations | ✅ rule-based (instant, offline-capable) |
| Semantic similarity (Kinesis ↔ Kafka) | ✅ tech-family KB + optional LLM blend |
| Claim verification (GitHub + LinkedIn) | ✅ free public APIs |
| Tier A/B/C classification | ✅ |
| Tailored interview question generation | ✅ via Groq |
| Streamlit web UI | ✅ |
| Rich terminal CLI | ✅ |
| Offline / no-API-key mode | ✅ `--no-llm` flag |

---

## Quickstart

### 1. Get a free Groq API key

1. Visit [console.groq.com](https://console.groq.com/keys)
2. Sign up — **no credit card needed**
3. Create a key (starts with `gsk_...`)

### 2. Install

```bash
pip install -r requirements.txt
```

### 3. Set your key

```bash
export GROQ_API_KEY="gsk_..."
```

### 4. Run

```bash
# Terminal demo (built-in sample data)
python -m src.cli demo

# Streamlit web UI
streamlit run app.py

# Evaluate a real resume
python -m src.cli evaluate --resume resume.txt --jd jd.txt

# With GitHub verification
python -m src.cli evaluate --resume resume.txt --jd jd.txt --verify

# Offline (no API key, rule-based scoring only)
python -m src.cli demo --no-llm
```

---

## Python API

```python
from src.parser import ResumeParser
from src.question_generator import TieringEngine
from src.verification import VerificationEngine

# 1. Parse
parser = ResumeParser()
resume = parser.parse_resume_from_file("resume.txt")
jd     = parser.parse_jd(open("jd.txt").read())

# 2. Verify (optional, no key required for public profiles)
with VerificationEngine() as ve:
    verification = ve.verify(
        github_url=resume.github_url,
        required_skills=jd.required_skills,
    )

# 3. Full evaluation
engine = TieringEngine()
ev = engine.evaluate(resume, jd, verification)

print(f"Tier: {ev.tier.value}")
print(f"Composite: {ev.scores.composite_score:.1f}/100")
print(f"\nExact Match {ev.scores.exact_match}/100: {ev.scores.exact_match_reason}")
print(f"Semantic {ev.scores.semantic_similarity}/100: {ev.scores.semantic_similarity_reason}")

for q in ev.interview_questions:
    print(f"\n[{q.category}] {q.question}")
```

---

## Scoring Model

### 4 Dimensions

| Dimension | Weight | How it works |
|-----------|--------|-------------|
| **Exact Match** | 30% | Keyword overlap: required/preferred skills vs resume |
| **Semantic Similarity** | 30% | Tech-family knowledge base + optional LLM blend |
| **Achievement Impact** | 25% | Regex patterns for %, $, scale, impact verbs |
| **Ownership/Leadership** | 15% | Language signals: "architected", "led team of N", etc. |

### How Semantic Similarity Works

The core challenge: recognising that **AWS Kinesis** experience is relevant for a **Kafka** role.

The system uses a **Technology Family knowledge base** mapping skills to conceptual domains:
```python
"message_queue": ["kafka", "rabbitmq", "activemq", "kinesis", "sqs", "pulsar", ...]
"container_orchestration": ["kubernetes", "ecs", "nomad", ...]
"cloud_aws": ["aws", "ec2", "s3", "kinesis", ...]
```

Candidates score based on how many of the JD's technology domains their background covers — regardless of the specific tool.

### Tier Classification

```
Tier A  composite ≥ 75  AND  exact_match ≥ 60  AND  sufficient experience  →  Fast-track
Tier B  composite ≥ 55  (or 45+ with good experience)                       →  Technical screen
Tier C  everything else                                                       →  Needs evaluation
```

---

## Running Tests (offline — no API key needed)

```bash
python tests/test_scoring.py
```

15 tests, all pure rule-based logic, no network calls:
- Exact match precision
- ✅ **Kinesis experience counting toward Kafka requirement** (the hard semantic test)
- Achievement pattern detection
- Ownership signal detection
- Tier A/B/C classification

---

## Project Structure

```
resume_ai_free/
├── src/
│   ├── models.py              # Data structures
│   ├── groq_client.py         # Thin Groq API wrapper (free LLM)
│   ├── parser.py              # Resume & JD parsing via Llama 3
│   ├── scoring.py             # 4-dimensional scoring engine
│   ├── verification.py        # GitHub (public API) + LinkedIn check
│   └── question_generator.py  # Tiering + tailored interview Q generation
├── tests/
│   └── test_scoring.py        # 15 unit tests (offline)
├── app.py                     # Streamlit web UI
├── requirements.txt
└── README.md
```

---

## Cost Summary

| Component | Cost |
|-----------|------|
| Groq LLM API | **Free** (14,400 req/day free tier) |
| GitHub API | **Free** (60 req/hr unauth, 5000/hr with free token) |
| LinkedIn check | **Free** (HTTP reachability only) |
| Rule-based scoring | **Free** (no API, instant) |

**Total: $0**

