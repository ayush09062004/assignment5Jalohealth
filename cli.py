"""
CLI — AI Resume Shortlisting & Interview Assistant (Free Edition)
=================================================================
Usage:
  python -m src.cli demo                            # built-in demo
  python -m src.cli evaluate --resume r.txt --jd jd.txt
  python -m src.cli evaluate --resume r.txt --jd jd.txt --verify
"""

import os
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import Tier

app = typer.Typer(help="AI Resume Shortlisting — powered by Groq (free)")
console = Console()

TIER_STYLE = {Tier.A: "bold green", Tier.B: "bold yellow", Tier.C: "bold red"}
TIER_LABEL = {Tier.A: "🚀 Tier A — Fast Track",
              Tier.B: "🔍 Tier B — Tech Screen",
              Tier.C: "📋 Tier C — Needs Eval"}


def _clr(score: float) -> str:
    return "green" if score >= 75 else ("yellow" if score >= 50 else "red")


def _bar(score: float) -> str:
    filled = int(score // 10)
    return "█" * filled + "░" * (10 - filled)


def _print_scores(scores) -> None:
    t = Table(title="📊 Score Breakdown", box=box.ROUNDED, show_lines=True)
    t.add_column("Dimension", style="bold", min_width=22)
    t.add_column("Score", justify="center", width=12)
    t.add_column("Explanation", max_width=68)

    rows = [
        ("Exact Match",          scores.exact_match,          scores.exact_match_reason),
        ("Semantic Similarity",  scores.semantic_similarity,  scores.semantic_similarity_reason),
        ("Achievement Impact",   scores.achievement_impact,   scores.achievement_impact_reason),
        ("Ownership/Leadership", scores.ownership_leadership, scores.ownership_leadership_reason),
    ]
    for name, val, reason in rows:
        t.add_row(
            name,
            Text(f"{val:5.1f}\n{_bar(val)}", style=_clr(val), justify="center"),
            reason,
        )

    c = scores.composite_score
    t.add_row(
        "[bold]COMPOSITE[/bold]",
        Text(f"{c:5.1f}\n{_bar(c)}", style=_clr(c), justify="center"),
        "Weighted: Exact×30% + Semantic×30% + Achievement×25% + Ownership×15%",
    )
    console.print(t)


def _print_eval(ev) -> None:
    style = TIER_STYLE[ev.tier]
    console.print(Panel(
        f"[bold]{ev.candidate_name}[/bold]  →  [italic]{ev.job_title}[/italic]\n"
        f"[{style}]{TIER_LABEL[ev.tier]}[/{style}]  |  "
        f"Composite: [{_clr(ev.scores.composite_score)}]{ev.scores.composite_score:.1f}/100[/{_clr(ev.scores.composite_score)}]\n\n"
        f"[dim]{ev.tier_reason}[/dim]",
        title="🎯 Candidate Evaluation",
        border_style=style,
    ))

    _print_scores(ev.scores)

    if ev.green_flags or ev.red_flags:
        console.print("\n[bold]📌 Flags[/bold]")
        for g in ev.green_flags:
            console.print(f"  ✅ [green]{g}[/green]")
        for r in ev.red_flags:
            console.print(f"  ⚠️  [red]{r}[/red]")

    if ev.verification:
        v = ev.verification
        console.print(Panel(
            f"Credibility: [{_clr(v.overall_credibility)}]{v.overall_credibility}/100[/{_clr(v.overall_credibility)}]\n"
            + (f"GitHub: {v.github_notes}\n" if v.github_notes else "")
            + (f"LinkedIn: {v.linkedin_notes}" if v.linkedin_notes else ""),
            title="🔎 Claim Verification",
            border_style="blue",
        ))

    if ev.interview_questions:
        console.print(f"\n[bold]🎤 Interview Questions — {len(ev.interview_questions)} generated[/bold]")
        cat_c = {"technical": "cyan", "behavioral": "magenta", "situational": "yellow"}
        dif_c = {"easy": "green", "medium": "yellow", "hard": "red"}
        for i, q in enumerate(ev.interview_questions, 1):
            console.print(Panel(
                f"[{dif_c.get(q.difficulty,'white')}][{q.difficulty.upper()}][/{dif_c.get(q.difficulty,'white')}]  "
                f"[{cat_c.get(q.category,'white')}][{q.category.upper()}][/{cat_c.get(q.category,'white')}]\n\n"
                f"[bold]{q.question}[/bold]\n\n"
                f"[dim]Why:[/dim] {q.rationale}\n"
                f"[dim]Expected:[/dim] {q.expected_answer_hints}",
                title=f"Q{i}",
                border_style=cat_c.get(q.category, "white"),
            ))

    console.print(Panel(ev.overall_recommendation, title="📋 Recommendation", border_style="bold"))


# ────────────────────────────────────────────────────────────────────────────

SAMPLE_RESUME = """Alex Chen
alex.chen@email.com | +1-555-0192 | github.com/alexchen-dev | linkedin.com/in/alexchendev

SUMMARY
Senior Software Engineer with 6 years building distributed systems and data pipelines.

SKILLS
Python, Go, Kubernetes, Docker, AWS (EC2, S3, Lambda, Kinesis, ECS), PostgreSQL, Redis,
RabbitMQ, Terraform, GitHub Actions, gRPC, FastAPI, Prometheus, Grafana, Datadog

EXPERIENCE

Senior Software Engineer — DataStream Inc (2021–Present, 3 years)
- Architected a real-time event processing pipeline using AWS Kinesis: 2M+ events/day
- Led migration of monolith to microservices; reduced deployment time by 70%
- Improved uptime from 99.1% to 99.97% across 3 critical services
- Mentored team of 4 junior engineers; 2 promoted to mid-level within 18 months
- Built internal developer platform — reduced new service setup from 2 days to 20 minutes
Achievements: Saved $180K/year in cloud costs via spot-instance migration

Software Engineer — CloudBase (2019–2021, 2 years)
- Built REST APIs serving 500K daily active users, p99 latency <50ms
- Redis caching reduced database load by 60%
- Improved checkout conversion by 12% through API performance optimization

EDUCATION
B.S. Computer Science, UC Berkeley, 2018
CERTIFICATIONS: AWS Solutions Architect Associate (2022)
"""

SAMPLE_JD = """Backend Engineer — Streaming Platform
Company: StreamCorp

REQUIRED:
- 4+ years backend engineering
- Apache Kafka or similar message queue (RabbitMQ, Kinesis, SQS)
- Kubernetes and container orchestration
- Python or Go
- PostgreSQL or similar relational database
- Distributed systems at scale

PREFERRED:
- AWS or GCP experience
- Terraform / Infrastructure as Code
- Monitoring: Datadog, Prometheus, Grafana
- Streaming/media domain experience

RESPONSIBILITIES:
- Design and maintain large-scale data ingestion pipelines
- Build Kafka-based event streaming infrastructure
- Drive reliability improvements across distributed services
- Mentor junior engineers and contribute to technical roadmap

Min: Bachelor's in CS or equivalent
"""


@app.command()
def demo(
    verify: bool = typer.Option(False, "--verify", help="Run live GitHub/LinkedIn verification"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Use rule-based scoring only (no Groq calls)"),
):
    """Run a full demo with built-in sample resume and JD."""
    console.print("[bold blue]🤖 AI Resume Shortlisting — Free Edition (Groq + Llama 3)[/bold blue]\n")

    from .parser import ResumeParser
    from .question_generator import TieringEngine
    from .verification import VerificationEngine

    with console.status("Parsing resume & JD..."):
        parser = ResumeParser()
        resume = parser.parse_resume(SAMPLE_RESUME)
        jd = parser.parse_jd(SAMPLE_JD)

    console.print(f"[green]✓[/green] {resume.name} | {resume.years_of_experience}yr | {len(resume.skills)} skills\n")

    verification = None
    if verify and (resume.github_url or resume.linkedin_url):
        with console.status("Verifying claims..."):
            with VerificationEngine() as ve:
                verification = ve.verify(resume.github_url, resume.linkedin_url, jd.required_skills)
        console.print("[green]✓[/green] Verification done\n")

    with console.status("Scoring & generating interview questions via Groq (free)..."):
        engine = TieringEngine(use_llm_augmentation=not no_llm)
        ev = engine.evaluate(resume, jd, verification)

    _print_eval(ev)


@app.command()
def evaluate(
    resume: Path = typer.Option(..., help="Resume file (.txt or .pdf)"),
    jd: Path    = typer.Option(..., help="Job description file (.txt)"),
    verify: bool = typer.Option(False, "--verify"),
    github_token: str = typer.Option("", envvar="GITHUB_TOKEN"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip Groq calls (offline mode)"),
):
    """Evaluate a resume against a job description."""
    from .parser import ResumeParser
    from .question_generator import TieringEngine
    from .verification import VerificationEngine

    console.print("[bold blue]🤖 AI Resume Shortlisting — Free Edition[/bold blue]\n")

    with console.status("Parsing..."):
        parser = ResumeParser()
        parsed_resume = parser.parse_resume_from_file(resume)
        parsed_jd = parser.parse_jd(jd.read_text(encoding="utf-8"))

    console.print(f"[green]✓[/green] {parsed_resume.name} | JD: {parsed_jd.title}\n")

    verification = None
    if verify:
        with console.status("Verifying..."):
            token = github_token or os.environ.get("GITHUB_TOKEN")
            with VerificationEngine(github_token=token) as ve:
                verification = ve.verify(
                    parsed_resume.github_url,
                    parsed_resume.linkedin_url,
                    parsed_jd.required_skills,
                )

    with console.status("Scoring & generating questions..."):
        engine = TieringEngine(use_llm_augmentation=not no_llm)
        ev = engine.evaluate(parsed_resume, parsed_jd, verification)

    _print_eval(ev)


if __name__ == "__main__":
    app()
