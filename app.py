"""
Streamlit UI — AI Resume Shortlisting & Interview Assistant
Free Edition: powered by Groq (free API) + Llama 3.3 70B

Run: streamlit run app.py
"""

import json
import os
import sys
import types

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
    """Return color based on score value, handling string inputs."""
    # Convert to float if it's a string
    if isinstance(s, str):
        try:
            s = float(s)
        except ValueError:
            s = 0.0
    return "#22c55e" if s >= 75 else ("#f59e0b" if s >= 50 else "#ef4444")


def score_bar(s: float, label: str, reason: str):
    """Display a score bar with label and reason."""
    # Convert to float if it's a string
    if isinstance(s, str):
        try:
            s = float(s)
        except ValueError:
            s = 0.0
    
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
        resume_text = st.text_area(
            "Resume text",  # Non-empty label
            value=DEMO_RESUME, 
            height=360, 
            label_visibility="collapsed"
        )
    else:
        up = st.file_uploader("Upload .txt or .pdf", type=["txt", "pdf"])
        resume_text = ""
        if up:
            resume_text = up.read().decode("utf-8", errors="replace") if up.name.endswith(".txt") else ""
            if not resume_text:
                st.warning("PDF text extraction requires PyPDF2. Paste text instead.")
        resume_text = st.text_area(
            "Or paste resume text", 
            value=resume_text, 
            height=300
        )

with col_r:
    st.subheader("💼 Job Description")
    if use_demo:
        jd_text = st.text_area(
            "Job description text",  # Non-empty label
            value=DEMO_JD, 
            height=360, 
            label_visibility="collapsed"
        )
    else:
        jd_text = st.text_area(
            "Paste JD text", 
            height=360
        )

st.markdown("---")

ready = (api_key or offline_mode) and resume_text and jd_text
if not ready:
    if not api_key and not offline_mode:
        st.info("👈 Enter your free Groq API key in the sidebar, or enable **Offline mode** to run without one.")

evaluate_btn = st.button("🚀 Evaluate Candidate", type="primary", disabled=not ready)

# ── Evaluation ─────────────────────────────────────────────────────────────────

if evaluate_btn and ready:
    # If offline mode, stub out groq so no network call is made
    if offline_mode:
        fake_groq = types.ModuleType("groq")
        sys.modules.setdefault("groq", fake_groq)

    sys.path.insert(0, ".")
    
    # Import modules with error handling
    try:
        from src.parser import ResumeParser
        from src.question_generator import TieringEngine
        from src.verification import VerificationEngine
    except ImportError as e:
        st.error(f"Failed to import required modules: {e}")
        st.error("Make sure all source files are in the correct location.")
        st.stop()

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
    if run_verify and not offline_mode and hasattr(resume, 'github_url') and (resume.github_url or resume.linkedin_url):
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

    tier_colors = {"A": "#22c55e", "B": "#f59e0b", "C": "#ef4444"}
    tier_labels = {"A": "🚀 Tier A — Fast Track",
                   "B": "🔍 Tier B — Tech Screen",
                   "C": "📋 Tier C — Needs Eval"}

    # Safely access attributes with defaults
    candidate_name = getattr(ev, 'candidate_name', 'Unknown')
    tier_value = getattr(ev, 'tier', None)
    if tier_value and hasattr(tier_value, 'value'):
        tier = tier_value.value
    else:
        tier = 'C'  # Default
    
    composite_score = getattr(ev.scores, 'composite_score', 0) if hasattr(ev, 'scores') else 0
    if isinstance(composite_score, str):
        try:
            composite_score = float(composite_score)
        except ValueError:
            composite_score = 0.0
    
    years_exp = getattr(resume, 'years_of_experience', 0)
    skills_count = len(getattr(resume, 'skills', []))
    
    tier_reason = getattr(ev, 'tier_reason', 'No reason provided')

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Candidate", candidate_name)
    c2.markdown(
        f'<div class="metric-label">Tier</div>'
        f'<div style="color:{tier_colors.get(tier, "#ef4444")};font-weight:700;font-size:1.1rem">'
        f'{tier_labels.get(tier, "📋 Tier C — Needs Eval")}</div>',
        unsafe_allow_html=True,
    )
    c3.metric("Composite Score", f"{composite_score:.1f} / 100")
    c4.metric("Experience", f"{years_exp:.1f} yr")
    c5.metric("Skills", f"{skills_count} detected")

    st.caption(tier_reason)

    st.markdown("---")
    st.subheader("📊 Score Breakdown")
    
    # Safely access score attributes
    if hasattr(ev, 'scores'):
        score_attrs = [
            ('exact_match', 'Exact Match'),
            ('semantic_similarity', 'Semantic Similarity'),
            ('achievement_impact', 'Achievement Impact'),
            ('ownership_leadership', 'Ownership/Leadership')
        ]
        
        for attr_name, display_name in score_attrs:
            score_value = getattr(ev.scores, attr_name, 0)
            reason_value = getattr(ev.scores, f'{attr_name}_reason', 'No reason provided')
            score_bar(score_value, display_name, reason_value)
    else:
        st.warning("No score data available")

    # Flags
    green_flags = getattr(ev, 'green_flags', [])
    red_flags = getattr(ev, 'red_flags', [])
    
    if green_flags or red_flags:
        fg, fr = st.columns(2)
        with fg:
            st.subheader("✅ Strengths")
            for g in green_flags:
                st.success(g)
        with fr:
            st.subheader("⚠️ Concerns")
            for r in red_flags:
                st.error(r)

    # Verification
    if verification:
        st.markdown("---")
        st.subheader("🔎 Claim Verification")
        v = verification
        vc1, vc2 = st.columns(2)
        
        credibility = getattr(v, 'overall_credibility', 0)
        if isinstance(credibility, str):
            try:
                credibility = float(credibility)
            except ValueError:
                credibility = 0.0
                
        vc1.metric("Credibility Score", f"{credibility} / 100")
        vc1.caption(getattr(v, 'github_notes', 'No GitHub') or "No GitHub")
        vc2.caption(getattr(v, 'linkedin_notes', 'No LinkedIn') or "No LinkedIn")
        
        for flag in getattr(v, 'flags', []):
            st.warning(flag)

    # Interview Questions
    interview_questions = getattr(ev, 'interview_questions', [])
    if interview_questions:
        st.markdown("---")
        st.subheader(f"🎤 Interview Questions ({len(interview_questions)})")
        cat_icon = {"technical": "💻", "behavioral": "💬", "situational": "🏗️"}
        dif_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
        
        for i, q in enumerate(interview_questions, 1):
            category = getattr(q, 'category', 'technical')
            difficulty = getattr(q, 'difficulty', 'medium')
            question_text = getattr(q, 'question', 'No question provided')
            rationale = getattr(q, 'rationale', 'No rationale provided')
            expected = getattr(q, 'expected_answer_hints', 'No hints provided')
            
            label = (
                f"Q{i} {cat_icon.get(category,'•')} {dif_icon.get(difficulty,'•')} "
                f"[{category.upper()}] — {question_text[:75]}..."
            )
            with st.expander(label):
                st.markdown(f"**Question:** {question_text}")
                st.markdown(f"**Why this question:** _{rationale}_")
                st.info(f"**Expected answer:** {expected}")

    # Export
    st.markdown("---")
    
    # Prepare export data safely
    export = {
        "candidate": candidate_name,
        "job": getattr(ev, 'job_title', 'Unknown'),
        "tier": tier,
        "scores": {},
        "green_flags": green_flags,
        "red_flags": red_flags,
        "questions": []
    }
    
    # Add scores if available
    if hasattr(ev, 'scores'):
        for attr_name in ['exact_match', 'semantic_similarity', 'achievement_impact', 'ownership_leadership']:
            score_val = getattr(ev.scores, attr_name, 0)
            if isinstance(score_val, str):
                try:
                    score_val = float(score_val)
                except ValueError:
                    score_val = 0.0
            export['scores'][attr_name] = score_val
        
        composite = getattr(ev.scores, 'composite_score', 0)
        if isinstance(composite, str):
            try:
                composite = float(composite)
            except ValueError:
                composite = 0.0
        export['scores']['composite'] = composite
    
    # Add questions if available
    for q in interview_questions:
        export['questions'].append({
            "q": getattr(q, 'question', ''),
            "category": getattr(q, 'category', ''),
            "difficulty": getattr(q, 'difficulty', '')
        })
    
    st.download_button(
        "⬇️ Download JSON Report",
        data=json.dumps(export, indent=2),
        file_name=f"eval_{candidate_name.replace(' ', '_')}.json",
        mime="application/json",
    )
