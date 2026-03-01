"""
Evaluation & Scoring Engine
============================
4 scoring dimensions with full explainability.
Exact/Achievement/Ownership use pure rule-based logic (no API calls).
Semantic Similarity uses Groq (free) only when needed for nuance.
"""

import json
import re

from .models import ParsedResume, ParsedJD, ScoreBreakdown, Tier


# ---------------------------------------------------------------------------
# Technology family knowledge base — the key to Kafka ↔ Kinesis recognition
# ---------------------------------------------------------------------------
TECH_FAMILIES: dict[str, list[str]] = {
    "message_queue":           ["kafka", "rabbitmq", "activemq", "sqs", "pubsub", "nats",
                                 "kinesis", "eventbridge", "servicebus", "pulsar", "zeromq"],
    "container_orchestration": ["kubernetes", "k8s", "ecs", "nomad", "openshift",
                                 "docker swarm", "mesos", "fargate"],
    "relational_db":           ["postgresql", "postgres", "mysql", "mariadb", "oracle",
                                 "mssql", "sqlite", "aurora", "cockroachdb"],
    "nosql_db":                ["mongodb", "dynamodb", "cassandra", "couchdb", "firestore",
                                 "cosmosdb", "redis", "elasticsearch", "opensearch", "hbase"],
    "cloud_aws":               ["aws", "amazon web services", "ec2", "s3", "lambda",
                                 "rds", "cloudformation", "cdk", "eks", "ecs", "kinesis"],
    "cloud_gcp":               ["gcp", "google cloud", "gke", "bigquery", "cloud run",
                                 "dataflow", "pub/sub", "spanner"],
    "cloud_azure":             ["azure", "microsoft azure", "aks", "azure functions",
                                 "cosmos db", "azure devops", "blob storage"],
    "ci_cd":                   ["jenkins", "github actions", "gitlab ci", "circleci",
                                 "travis", "argo", "tekton", "spinnaker", "teamcity", "bamboo"],
    "monitoring":              ["datadog", "prometheus", "grafana", "splunk", "newrelic",
                                 "dynatrace", "cloudwatch", "elk", "kibana", "jaeger", "zipkin"],
    "ml_framework":            ["tensorflow", "pytorch", "keras", "sklearn", "scikit-learn",
                                 "jax", "huggingface", "xgboost", "lightgbm"],
    "frontend_framework":      ["react", "vue", "angular", "svelte", "nextjs", "nuxt", "remix"],
    "backend_framework":       ["django", "fastapi", "flask", "express", "nestjs",
                                 "spring boot", "rails", "gin", "fiber", "actix", "axum"],
    "language_jvm":            ["java", "kotlin", "scala", "groovy", "clojure"],
    "language_scripting":      ["python", "ruby", "perl", "php", "lua", "bash", "shell"],
    "language_compiled":       ["go", "golang", "rust", "c++", "c", "c#", ".net"],
    "language_typed_js":       ["typescript", "javascript", "node.js", "nodejs", "deno"],
    "infra_as_code":           ["terraform", "pulumi", "cdk", "cloudformation", "ansible",
                                 "puppet", "chef", "helm"],
    "data_pipeline":           ["spark", "flink", "beam", "airflow", "prefect", "dagster",
                                 "dbt", "fivetran", "stitch", "glue"],
    "version_control":         ["git", "github", "gitlab", "bitbucket", "svn"],
}


def _normalize(text: str) -> str:
    return text.lower().strip()


def _get_tech_family(skill: str) -> str | None:
    s = _normalize(skill)
    for family, members in TECH_FAMILIES.items():
        if any(m in s or s in m for m in members):
            return family
    return None


# ---------------------------------------------------------------------------
# Dimension 1 — Exact Match (pure rule-based)
# ---------------------------------------------------------------------------

def _compute_exact_match(resume: ParsedResume, jd: ParsedJD) -> tuple[float, str]:
    resume_skills_lower = {_normalize(s) for s in resume.skills}

    # Also scan experience descriptions for implicit skill mentions
    for exp in resume.experience:
        desc = _normalize(exp.get("description", ""))
        for skill in jd.required_skills + jd.preferred_skills:
            if _normalize(skill) in desc:
                resume_skills_lower.add(_normalize(skill))

    required = [_normalize(s) for s in jd.required_skills]
    preferred = [_normalize(s) for s in jd.preferred_skills]

    matched_req  = [s for s in required  if s in resume_skills_lower]
    matched_pref = [s for s in preferred if s in resume_skills_lower]
    missed_req   = [s for s in required  if s not in resume_skills_lower]

    if not required:
        return 50.0, "No required skills specified in JD; defaulting to neutral 50."

    req_ratio  = len(matched_req)  / len(required)
    pref_bonus = (len(matched_pref) / max(len(preferred), 1)) * 0.15
    score = min(100.0, (req_ratio + pref_bonus) * 100)

    reason = (
        f"Matched {len(matched_req)}/{len(required)} required skills "
        f"({', '.join(matched_req[:5]) or 'none'}). "
        + (f"Missing: {', '.join(missed_req[:5])}. " if missed_req else "All required skills present! ")
        + (f"Also matched {len(matched_pref)} preferred skills." if matched_pref else "")
    )
    return round(score, 1), reason


# ---------------------------------------------------------------------------
# Dimension 2 — Semantic Similarity (tech families + optional Groq LLM)
# ---------------------------------------------------------------------------

def _compute_semantic_similarity(
    resume: ParsedResume,
    jd: ParsedJD,
    use_llm: bool = True,
) -> tuple[float, str]:
    # Collect resume's tech families from skills + experience text
    all_resume_text = " ".join(
        exp.get("description", "") + " " + " ".join(exp.get("achievements", []))
        for exp in resume.experience
    ).lower()

    resume_families: set[str] = set()
    for s in resume.skills:
        fam = _get_tech_family(s)
        if fam:
            resume_families.add(fam)
    for family, members in TECH_FAMILIES.items():
        if any(m in all_resume_text for m in members):
            resume_families.add(family)

    # JD's tech families
    jd_families: set[str] = set()
    for s in jd.required_skills + jd.preferred_skills:
        fam = _get_tech_family(s)
        if fam:
            jd_families.add(fam)

    if not jd_families:
        rule_score = 50.0
        rule_reason = "No recognisable technology domains in JD; defaulting to neutral."
    else:
        covered = resume_families & jd_families
        # Cloud partial credit: AWS↔GCP↔Azure are different but adjacent
        cloud_families = {"cloud_aws", "cloud_gcp", "cloud_azure"}
        if (jd_families & cloud_families) and (resume_families & cloud_families):
            covered |= (jd_families & cloud_families)  # count all clouds as covered

        rule_score = min(100.0, (len(covered) / len(jd_families)) * 100)
        missed = jd_families - resume_families
        rule_reason = (
            f"Resume covers {len(covered)}/{len(jd_families)} technology domains. "
            + (f"Matched: {', '.join(sorted(covered)[:5])}. " if covered else "")
            + (f"Gap: {', '.join(sorted(missed)[:4])}." if missed else "Full domain coverage!")
        )

    if not use_llm:
        return round(rule_score, 1), rule_reason

    # LLM augmentation via Groq (free) — blended 40/60 with rule score
    try:
        llm_score, llm_reason = _llm_semantic(resume, jd, rule_score)
        final = round(0.60 * rule_score + 0.40 * llm_score, 1)
        return final, llm_reason
    except Exception:
        return round(rule_score, 1), rule_reason


def _llm_semantic(
    resume: ParsedResume, jd: ParsedJD, rule_score: float
) -> tuple[float, str]:
    from .groq_client import chat_json

    prompt = f"""You are an expert technical recruiter. Score SEMANTIC FIT (0-100) between this candidate and job.

JOB: {jd.title}
Required: {', '.join(jd.required_skills[:12])}
Preferred: {', '.join(jd.preferred_skills[:8])}

CANDIDATE skills: {', '.join(resume.skills[:25])}
Roles: {'; '.join(e.get('title','')+'@'+e.get('company','') for e in resume.experience[:4])}

Consider tech equivalences: Kinesis≈Kafka≈RabbitMQ (message queues), AWS≈GCP≈Azure (cloud), etc.
Rule-based pre-score: {rule_score}

Respond ONLY with JSON: {{"score": 72, "reason": "one concise sentence"}}"""

    data = chat_json(prompt, max_tokens=150)
    return float(data.get("score", rule_score)), data.get("reason", f"Semantic score: {rule_score}/100")


# ---------------------------------------------------------------------------
# Dimension 3 — Achievement Impact (pure rule-based)
# ---------------------------------------------------------------------------

QUANT_PATTERNS = [
    re.compile(r"\d+\s*%",                                           re.I),
    re.compile(r"\$[\d,]+[kmb]?",                                    re.I),
    re.compile(r"\d+[xX]\b",                                         re.I),
    re.compile(r"\b\d+\s*(users|customers|clients|engineers|"
               r"developers|servers|requests|transactions|tenants)\b", re.I),
    re.compile(r"\b(reduced|improved|increased|decreased|grew|"
               r"scaled|saved|cut|boosted|eliminated)\s+\w+\s+by\b", re.I),
    re.compile(r"\b(led|managed|owned|architected|designed|built)\s+"
               r"(team|system|platform|service|product)\b",           re.I),
    re.compile(r"\b(from scratch|zero to one|0 to 1|greenfield)\b",   re.I),
]


def _compute_achievement_impact(resume: ParsedResume) -> tuple[float, str]:
    all_achievements: list[str] = []
    for exp in resume.experience:
        all_achievements.extend(exp.get("achievements", []))
        # Also check description sentences for embedded metrics
        for sent in re.split(r"[.!?\n]", exp.get("description", "")):
            if any(p.search(sent) for p in QUANT_PATTERNS):
                all_achievements.append(sent.strip())

    if not all_achievements:
        return 20.0, (
            "No achievements extracted. Resume uses generic responsibility language only. "
            "Add quantified results (%, $, scale numbers) to improve this score."
        )

    hits = [a for a in all_achievements if any(p.search(a) for p in QUANT_PATTERNS)]
    ratio = len(hits) / len(all_achievements)
    count_bonus = min(20, len(hits) * 4)
    score = min(100.0, ratio * 80 + count_bonus)

    reason = (
        f"Found {len(hits)} quantified achievements out of {len(all_achievements)} statements. "
        + (f"Examples: {'; '.join(hits[:2])}." if hits else "")
        + (" Consider adding measurable outcomes to weak bullet points." if score < 60 else "")
    )
    return round(score, 1), reason


# ---------------------------------------------------------------------------
# Dimension 4 — Ownership / Leadership (pure rule-based)
# ---------------------------------------------------------------------------

OWNERSHIP_PATTERNS = [
    re.compile(r"\b(architect|architected|design|designed|built|created|"
               r"founded|launched|shipped|developed)\b",              re.I),
    re.compile(r"\b(led|lead|managed|mentored|coached|grew|growing)\s+"
               r"(team|engineers|developers|people|a\s+team)\b",      re.I),
    re.compile(r"\b(owned|responsible for|drove|drive|spearhead|"
               r"spearheaded|championed|initiated|established)\b",    re.I),
    re.compile(r"\b(cross-functional|stakeholder|executive|"
               r"c-level|director|vp)\b",                             re.I),
    re.compile(r"\b(roadmap|strategy|vision|okr|kpi)\b",              re.I),
    re.compile(r"\b(from scratch|greenfield|0 to 1|zero to one)\b",   re.I),
    re.compile(r"\b(independently|autonomously|sole engineer|"
               r"single-handedly)\b",                                 re.I),
    re.compile(r"\b(migration|refactor|rewrite|redesign|overhaul)\b", re.I),
]


def _compute_ownership_leadership(resume: ParsedResume) -> tuple[float, str]:
    full_text = " ".join([
        resume.summary,
        *[exp.get("description", "") + " " + " ".join(exp.get("achievements", []))
          for exp in resume.experience],
    ])

    matched: list[str] = []
    for pattern in OWNERSHIP_PATTERNS:
        m = pattern.search(full_text)
        if m:
            matched.append(m.group(0).lower())

    score = min(100, len(matched) * 17)

    reason = (
        f"Detected {len(matched)} ownership/leadership signals "
        f"({', '.join(dict.fromkeys(matched[:5]))}). "
        if matched else
        "No ownership language found. "
        "Add signals like 'architected', 'led team of N', 'owned X from scratch' to boost this score."
    )
    return round(score, 1), reason


# ---------------------------------------------------------------------------
# ScoringEngine — orchestrates all dimensions
# ---------------------------------------------------------------------------

class ScoringEngine:

    def __init__(self, use_llm_augmentation: bool = True):
        """
        use_llm_augmentation: if True, calls Groq for semantic blending.
        Set False for tests/offline use.
        """
        self.use_llm = use_llm_augmentation

    def score(self, resume: ParsedResume, jd: ParsedJD) -> ScoreBreakdown:
        exact,   exact_r   = _compute_exact_match(resume, jd)
        semantic, sem_r    = _compute_semantic_similarity(resume, jd, use_llm=self.use_llm)
        achieve, ach_r     = _compute_achievement_impact(resume)
        own,     own_r     = _compute_ownership_leadership(resume)
        return ScoreBreakdown(
            exact_match=exact,
            semantic_similarity=semantic,
            achievement_impact=achieve,
            ownership_leadership=own,
            exact_match_reason=exact_r,
            semantic_similarity_reason=sem_r,
            achievement_impact_reason=ach_r,
            ownership_leadership_reason=own_r,
        )

    def classify_tier(
        self, scores: ScoreBreakdown, resume: ParsedResume, jd: ParsedJD
    ) -> tuple[Tier, str]:
        composite = scores.composite_score
        exp_ok = resume.years_of_experience >= jd.min_years_experience * 0.8

        if composite >= 75 and exp_ok and scores.exact_match >= 60:
            tier = Tier.A
            reason = (
                f"Composite {composite:.1f}/100 with strong exact match ({scores.exact_match:.0f}) "
                f"and {resume.years_of_experience:.1f}yr experience. "
                "→ Fast-track to hiring manager."
            )
        elif composite >= 55 or (composite >= 45 and exp_ok):
            tier = Tier.B
            reason = (
                f"Composite {composite:.1f}/100 shows solid potential. "
                + ("Experience meets threshold. " if exp_ok
                   else f"{resume.years_of_experience:.1f}yr vs {jd.min_years_experience}yr required. ")
                + "→ Recommend 45-min technical screen."
            )
        else:
            tier = Tier.C
            gaps = []
            if scores.exact_match < 50:
                gaps.append(f"skill gap (exact match {scores.exact_match:.0f}/100)")
            if not exp_ok:
                gaps.append(f"under-experienced ({resume.years_of_experience:.1f}yr vs {jd.min_years_experience}yr)")
            reason = (
                f"Composite {composite:.1f}/100. "
                + (f"Concerns: {'; '.join(gaps)}. " if gaps else "")
                + "→ Needs further evaluation."
            )
        return tier, reason
