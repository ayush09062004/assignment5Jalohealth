"""
Claim Verification Engine
==========================
Verifies GitHub and LinkedIn claims using only free/public APIs.
- GitHub: public REST API (60 req/hr unauthenticated, 5000/hr with free token)
- LinkedIn: URL reachability check only (full scraping violates ToS)
"""

import re
import time
from typing import Optional

import httpx

from .models import VerificationResult


GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _extract_github_username(url: str) -> Optional[str]:
    url = url.strip().rstrip("/")
    m = re.search(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9\-]{0,37}[A-Za-z0-9])?)", url)
    if m:
        user = m.group(1)
        if user.lower() not in {"about", "features", "pricing", "explore", "login", "join",
                                  "orgs", "topics", "collections", "trending"}:
            return user
    return None


def _extract_linkedin_handle(url: str) -> Optional[str]:
    m = re.search(r"linkedin\.com/in/([A-Za-z0-9\-]+)", url)
    return m.group(1) if m else None


class VerificationEngine:

    def __init__(self, github_token: Optional[str] = None, timeout: float = 10.0):
        self.timeout = timeout
        headers = dict(GITHUB_HEADERS)
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        self._headers = headers

    def verify(
        self,
        github_url: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        required_skills: Optional[list[str]] = None,
    ) -> VerificationResult:
        result = VerificationResult()
        required_skills = required_skills or []

        with httpx.Client(
            headers=self._headers,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            if github_url:
                self._verify_github(github_url, required_skills, result, client)
            if linkedin_url:
                self._verify_linkedin(linkedin_url, result, client)

        signals = []
        if github_url:
            signals.append(result.github_authenticity_score)
        if linkedin_url:
            signals.append(80.0 if result.linkedin_reachable else 20.0)
        result.overall_credibility = round(
            sum(signals) / max(len(signals), 1), 1
        )
        return result

    # ------------------------------------------------------------------ GitHub

    def _verify_github(
        self,
        url: str,
        required_skills: list[str],
        result: VerificationResult,
        client: httpx.Client,
    ) -> None:
        username = _extract_github_username(url)
        if not username:
            result.github_active = False
            result.github_notes = f"Cannot parse username from: {url}"
            return

        try:
            user = client.get(f"{GITHUB_API}/users/{username}").raise_for_status().json()
        except Exception as e:
            result.github_active = False
            result.github_notes = f"GitHub profile not found or API error ({e})"
            result.github_authenticity_score = 5.0
            result.flags.append("GitHub profile unreachable or does not exist")
            return

        result.github_active = True
        result.github_repos_count = user.get("public_repos", 0)

        # Repos
        try:
            repos = client.get(
                f"{GITHUB_API}/users/{username}/repos?per_page=30&sort=pushed"
            ).raise_for_status().json()
        except Exception:
            repos = []

        languages: set[str] = set()
        for repo in repos[:15]:
            lang = repo.get("language")
            if lang:
                languages.add(lang.lower())

        # Recent activity
        recent_commits = 0
        try:
            events = client.get(
                f"{GITHUB_API}/users/{username}/events/public?per_page=30"
            ).raise_for_status().json()
            cutoff = time.time() - 90 * 86400
            recent_commits = sum(
                1 for e in events
                if e.get("type") == "PushEvent"
                and _parse_ts(e.get("created_at", "")) > cutoff
            )
        except Exception:
            pass

        result.github_recent_commits = recent_commits
        result.github_languages = sorted(languages)

        # --- Authenticity score ---
        score = 25.0  # profile exists

        if result.github_repos_count >= 10:  score += 20
        elif result.github_repos_count >= 5:  score += 12
        elif result.github_repos_count >= 1:  score += 5

        if recent_commits >= 15:  score += 25
        elif recent_commits >= 5: score += 15
        elif recent_commits >= 1: score += 8

        skill_langs = {_skill_to_lang(s) for s in required_skills}
        matched = skill_langs & {l.lower() for l in languages} - {None}  # type: ignore
        if matched:
            score += min(20, len(matched) * 7)

        account_age = _account_age_years(user.get("created_at", ""))
        if account_age >= 3:   score += 10
        elif account_age >= 1: score += 5

        result.github_authenticity_score = min(100.0, round(score, 1))

        flags = []
        if result.github_repos_count == 0:
            flags.append("No public repos — coding activity unverifiable")
        if recent_commits == 0:
            flags.append("No commits in 90 days — account may be inactive")
        if required_skills and not (skill_langs & {l.lower() for l in languages}):
            flags.append(
                f"GitHub languages ({', '.join(list(languages)[:4]) or 'none'}) "
                "don't match required skills — possible gap or private repos only"
            )

        result.flags.extend(flags)
        result.github_notes = (
            f"@{username} | Repos: {result.github_repos_count} | "
            f"Commits (90d): {recent_commits} | "
            f"Languages: {', '.join(list(languages)[:6]) or 'none detected'}"
        )

    # ---------------------------------------------------------------- LinkedIn

    def _verify_linkedin(
        self, url: str, result: VerificationResult, client: httpx.Client
    ) -> None:
        handle = _extract_linkedin_handle(url)
        if not handle:
            result.linkedin_reachable = False
            result.linkedin_notes = f"Invalid LinkedIn URL: {url}"
            result.flags.append("LinkedIn URL format is invalid")
            return

        try:
            resp = client.head(url, headers={"User-Agent": "Mozilla/5.0"})
            result.linkedin_reachable = resp.status_code in {200, 302, 301, 999}
        except Exception:
            result.linkedin_reachable = False

        result.linkedin_notes = (
            f"Profile {'reachable' if result.linkedin_reachable else 'unreachable'}: {url}. "
            "Note: Full scraping disabled (ToS) — manual verification recommended."
        )
        if not result.linkedin_reachable:
            result.flags.append(f"LinkedIn URL unreachable: {url}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts: str) -> float:
    try:
        from datetime import datetime, timezone
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _account_age_years(created_at: str) -> float:
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days / 365.25
    except Exception:
        return 0.0


def _skill_to_lang(skill: str) -> Optional[str]:
    mapping = {
        "python": "python", "javascript": "javascript", "typescript": "typescript",
        "java": "java", "go": "go", "golang": "go", "rust": "rust",
        "c++": "c++", "c#": "c#", "ruby": "ruby", "php": "php",
        "kotlin": "kotlin", "swift": "swift", "scala": "scala", "shell": "shell",
    }
    return mapping.get(skill.strip().lower())
