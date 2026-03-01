"""
Streamlit UI — AI Resume Shortlisting & Interview Assistant
Free Edition: powered by Groq (free API) + Llama 3.3 70B

Run: streamlit run app.py
"""

import json
import os

import streamlit as st

st.set_page_config(
    page_title="AI Resume Shortlisting (Free)",
    page_icon="🤖",
    layout="wide",
)

st.markdown("""
<style>
.metric-label { font-size: 0.8rem; color: #888; }
.score-bar-bg { background: #2d2d2d; border-radius:4px; height:8px; margin:3px 0 6px; }
.green { color: #22c55e; } .yellow { color: #f59e0b; } .red { color: #ef4444; }
</style>
""", unsafe_allow_html=True)


def score_color(s: float) -> str:
    return "#22c55e" if s >= 75 else ("#f59e0b" if s >= 50 else "#ef4444")


def score_bar(s: float, label: str, reason: str):
    col1, col2 = st.columns([1, 3])
    with col1:
        st.markdown(f"**{label}**")
        st.markdown(
            f'<div class="score-bar-bg"><div style="width:{s}%;height:8px;'
            f'background:{score_color(s)};border-radius:4px;"></div></div>'
            f'<span style="color:{score_color(s)};font-weight:600">{s:.1f}/100</span>',
            unsafe_allow_html=True,
        )
    with col2:
        st.info(reason, icon="ℹ️")


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configuration")
    st.markdown(
        "**Groq API Key** (free)\n"
        "Get yours at [console.groq.com](https://console.groq.com/keys) — no credit card needed."
    )
    api_key = st.text_input(
        "GROQ_API_KEY",
        type="password",
        value=os.environ.get("GROQ_API_KEY", ""),
    )
    if api_key:
        os.environ["GROQ_API_KEY"] = api_key

    github_token = st.text_input(
        "GitHub Token (optional — increases rate limits)",
        type="password",
        value=os.environ.get("GITHUB_TOKEN", ""),
    )
    run_verify = st.checkbox("Run claim verification", value=False)
    offline_mode = st.checkbox(
        "Offline mode (rule-based only, no Groq calls)",
        value=False,
        help="Skips LLM calls — useful for testing without an API key",
    )

    st.markdown("---")
    st.caption("**Scoring weights**")
    st.caption("Exact Match · 30%")
    st.caption("Semantic Similarity · 30%")
    st.caption("Achievement Impact · 25%")
    st.caption("Ownership / Leadership · 15%")
    st.markdown("---")
    use_demo = st.checkbox("Use built-in demo data", value=True)

# ── Demo content ───────────────────────────────────────────────────────────────

DEMO_RESUME = """Alex Chen
alex.chen@email.com | github.com/alexchen-dev | linkedin.com/in/alexchendev

SUMMARY
Senior Software Engineer with 6 years building distributed systems and data pipelines.

SKILLS
Python, Go, Kubernetes, Docker, AWS (EC2, Kinesis, Lambda, ECS), PostgreSQL, Redis,
RabbitMQ, Terraform, GitHub Actions, gRPC, FastAPI, Prometheus, Grafana

EXPERIENCE
Senior Software Engineer — DataStream Inc (2021–Present, 3 years)
- Architected real-time event pipeline using AWS Kinesis: 2M+ events/day
- Led migration to microservices; reduced deployment time by 70%, uptime to 99.97%
- Mentored team of 4 engineers; 2 promoted within 18 months
- Saved $180K/year through spot-instance migration

Software Engineer — CloudBase (2019–2021, 2 years)
- Built APIs serving 500K DAU with p99 <50ms
- Redis caching cut DB load by 60%; improved checkout conversion by 12%

EDUCATION: B.S. CS, UC Berkeley 2018
CERTIFICATIONS: AWS Solutions Architect Associate (2022)
"""

DEMO_JD = """Backend Engineer — Streaming Platform
Company: StreamCorp

REQUIRED:
- 4+ years backend engineering
- Apache Kafka or similar (RabbitMQ, Kinesis, SQS)
- Kubernetes and Docker
- Python or Go
- PostgreSQL
- Distributed systems experience

PREFERRED:
- AWS or GCP
- Terraform / IaC
- Datadog, Prometheus, Grafana

RESPONSIBILITIES:
- Design data ingestion pipelines
- Build Kafka-based streaming infrastructure
- Drive reliability improvements
- Mentor junior engineers
"""

# ── Input columns ──────────────────────────────────────────────────────────────

col_l, col_r = st.columns(2)

with col_l:
    st.subheader("📄 Resume")
    if use_demo:
        resume_text = st.text_area("", value=DEMO_RESUME, height=360, label_visibility="collapsed")
    else:
        up = st.file_uploader("Upload .txt or .pdf", type=["txt", "pdf"])
        resume_text = ""
        if up:
            resume_text = up.read().decode("utf-8", errors="replace") if up.name.endswith(".txt") else ""
            if not resume_text:
                st.warning("PDF text extraction requires PyPDF2. Paste text instead.")
        resume_text = st.text_area("Or paste resume text", value=resume_text, height=300)

with col_r:
    st.subheader("💼 Job Description")
    if use_demo:
        jd_text = st.text_area("", value=DEMO_JD, height=360, label_visibility="collapsed")
    else:
        jd_text = st.text_area("Paste JD text", height=360)

st.markdown("---")

ready = (api_key or offline_mode) and resume_text and jd_text
if not ready:
    if not api_key and not offline_mode:
        st.info("👈 Enter your free Groq API key in the sidebar, or enable **Offline mode** to run without one.")

evaluate_btn = st.button("🚀 Evaluate Candidate", type="primary", disabled=not ready)

# ── Evaluation ─────────────────────────────────────────────────────────────────

if evaluate_btn and ready:
    import sys, types
    # If offline mode, stub out groq so no network call is made
    if offline_mode:
        fake_groq = types.ModuleType("groq")
        sys.modules.setdefault("groq", fake_groq)

    sys.path.insert(0, ".")
    from src.parser import ResumeParser
    from src.question_generator import TieringEngine
    from src.verification import VerificationEngine

    with st.spinner("Parsing resume & JD..."):
        try:
            parser = ResumeParser()
            resume = parser.parse_resume(resume_text)
            jd = parser.parse_jd(jd_text)
            st.success(f"✓ Parsed: **{resume.name}** | {resume.years_of_experience:.1f}yr | {len(resume.skills)} skills")
        except Exception as e:
            st.error(f"Parse error: {e}")
            st.stop()

    verification = None
    if run_verify and not offline_mode and (resume.github_url or resume.linkedin_url):
        with st.spinner("Verifying claims..."):
            try:
                token = github_token or os.environ.get("GITHUB_TOKEN") or None
                with VerificationEngine(github_token=token) as ve:
                    verification = ve.verify(
                        github_url=resume.github_url,
                        linkedin_url=resume.linkedin_url,
                        required_skills=jd.required_skills,
                    )
            except Exception as e:
                st.warning(f"Verification error: {e}")

    with st.spinner("Scoring & generating interview questions..."):
        try:
            engine = TieringEngine(use_llm_augmentation=not offline_mode)
            ev = engine.evaluate(resume, jd, verification)
        except Exception as e:
            st.error(f"Evaluation error: {e}")
            st.stop()

    # ── Display results ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 🎯 Evaluation Results")

    tier_colors  = {"A": "#22c55e", "B": "#f59e0b", "C": "#ef4444"}
    tier_labels  = {"A": "🚀 Tier A — Fast Track",
                    "B": "🔍 Tier B — Tech Screen",
                    "C": "📋 Tier C — Needs Eval"}

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Candidate", ev.candidate_name)
    c2.markdown(
        f'<div class="metric-label">Tier</div>'
        f'<div style="color:{tier_colors[ev.tier.value]};font-weight:700;font-size:1.1rem">'
        f'{tier_labels[ev.tier.value]}</div>',
        unsafe_allow_html=True,
    )
    c3.metric("Composite Score", f"{ev.scores.composite_score:.1f} / 100")
    c4.metric("Experience", f"{resume.years_of_experience:.1f} yr")
    c5.metric("Skills", f"{len(resume.skills)} detected")

    st.caption(ev.tier_reason)

    st.markdown("---")
    st.subheader("📊 Score Breakdown")
    score_bar("Exact Match",          ev.scores.exact_match,          ev.scores.exact_match_reason)
    score_bar("Semantic Similarity",  ev.scores.semantic_similarity,  ev.scores.semantic_similarity_reason)
    score_bar("Achievement Impact",   ev.scores.achievement_impact,   ev.scores.achievement_impact_reason)
    score_bar("Ownership/Leadership", ev.scores.ownership_leadership, ev.scores.ownership_leadership_reason)

    # Flags
    if ev.green_flags or ev.red_flags:
        fg, fr = st.columns(2)
        with fg:
            st.subheader("✅ Strengths")
            for g in ev.green_flags:
                st.success(g)
        with fr:
            st.subheader("⚠️ Concerns")
            for r in ev.red_flags:
                st.error(r)

    # Verification
    if verification:
        st.markdown("---")
        st.subheader("🔎 Claim Verification")
        v = verification
        vc1, vc2 = st.columns(2)
        vc1.metric("Credibility Score", f"{v.overall_credibility} / 100")
        vc1.caption(v.github_notes or "No GitHub")
        vc2.caption(v.linkedin_notes or "No LinkedIn")
        for flag in v.flags:
            st.warning(flag)

    # Interview Questions
    if ev.interview_questions:
        st.markdown("---")
        st.subheader(f"🎤 Interview Questions ({len(ev.interview_questions)})")
        cat_icon = {"technical": "💻", "behavioral": "💬", "situational": "🏗️"}
        dif_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
        for i, q in enumerate(ev.interview_questions, 1):
            label = (
                f"Q{i} {cat_icon.get(q.category,'•')} {dif_icon.get(q.difficulty,'•')} "
                f"[{q.category.upper()}] — {q.question[:75]}..."
            )
            with st.expander(label):
                st.markdown(f"**Question:** {q.question}")
                st.markdown(f"**Why this question:** _{q.rationale}_")
                st.info(f"**Expected answer:** {q.expected_answer_hints}")

    # Export
    st.markdown("---")
    export = {
        "candidate": ev.candidate_name,
        "job": ev.job_title,
        "tier": ev.tier.value,
        "scores": {
            "exact_match": ev.scores.exact_match,
            "semantic_similarity": ev.scores.semantic_similarity,
            "achievement_impact": ev.scores.achievement_impact,
            "ownership_leadership": ev.scores.ownership_leadership,
            "composite": ev.scores.composite_score,
        },
        "green_flags": ev.green_flags,
        "red_flags": ev.red_flags,
        "questions": [
            {"q": q.question, "category": q.category, "difficulty": q.difficulty}
            for q in ev.interview_questions
        ],
    }
    st.download_button(
        "⬇️ Download JSON Report",
        data=json.dumps(export, indent=2),
        file_name=f"eval_{ev.candidate_name.replace(' ', '_')}.json",
        mime="application/json",
    )
