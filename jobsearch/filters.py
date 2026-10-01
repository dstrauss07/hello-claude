"""Rule-based pre-scoring: title relevance, commute/remote, family fit. Cheap and
deterministic, so it runs on every posting before the best ones go to Claude."""
from __future__ import annotations

import re

from .models import Job


def _has(text: str, phrase: str) -> bool:
    # Word-boundary match so "hr" doesn't hit "through", "vp" doesn't hit "mvp".
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase.lower())}", text) is not None


def _any(text: str, phrases: list[str]) -> list[str]:
    return [p for p in phrases if _has(text, p)]


def classify_location(job: Job, loc_cfg: dict) -> str:
    """remote | near | ok | far | benchmark_area | relocation"""
    loc = (job.location or "").lower()
    text = f"{job.title} {job.description[:3000]}".lower()
    if job.workplace == "remote" or job.remote or _has(loc, "remote") or _has(loc, "anywhere"):
        return "remote"
    if not job.workplace and re.search(r"\b(fully|100%) remote\b|\bremote[- ]first\b", text):
        return "remote"
    for tier in ("near", "ok", "far", "benchmark_area"):
        if _any(loc, loc_cfg.get(tier, [])):
            return tier
    if not loc:
        return "far"  # unknown location: don't reward it
    return "relocation"


def workplace(job: Job) -> str:
    if job.workplace:
        return job.workplace
    text = f"{job.title} {job.location} {job.description[:3000]}".lower()
    if _has(text, "hybrid") or _has(text, "telework"):
        return "hybrid"
    return "onsite"


def score(job: Job, cfg: dict) -> Job | None:
    """Returns the job with rule_score/reasons/commute set, or None if excluded."""
    w, rules = cfg["weights"], cfg["title_rules"]
    title = job.title.lower()
    if _any(title, rules["exclude"]):
        return None

    reasons: list[str] = []
    s = 30  # baseline

    if _any(title, rules["strong"]):
        s += w["title_strong"]
        reasons.append("title matches I-O/OD focus")
    elif _any(title, rules["related"]):
        s += w["title_related"]
        reasons.append("adjacent HR/people role")
    else:
        return None  # keyword APIs return lots of noise; drop unrelated titles

    commute = classify_location(job, cfg["location"])
    job.commute = commute
    mode = "remote" if commute == "remote" else workplace(job)
    if commute == "remote":
        s += w["remote"]
        reasons.append("remote")
    elif commute in ("near", "ok", "far"):
        s += w.get(f"{mode}_{commute}", 0)
        reasons.append(f"{mode}, {commute} commute")
    elif commute == "benchmark_area":
        s += w["benchmark_area"]
        reasons.append("Durham/Triangle area (same move as OPM)")
    else:
        s += w["relocation"]
        reasons.append("requires relocation")

    text = f"{job.title} {job.description}".lower()
    pos = _any(text, cfg["family_signals"]["positive"])
    neg = _any(text, cfg["family_signals"]["negative"])
    if pos:
        s += min(len(pos), 3) * w["family_positive"]
        reasons.append("family-friendly: " + ", ".join(pos[:3]))
    if neg:
        s += min(len(neg), 2) * w["family_negative"]
        reasons.append("watch out: " + ", ".join(neg[:2]))

    job.rule_score = max(0, min(100, s))
    job.reasons = reasons
    return job


def dedupe(jobs: list[Job]) -> list[Job]:
    """Same title+company from several sources: keep the richest description."""
    best: dict[str, Job] = {}
    for j in jobs:
        cur = best.get(j.id)
        if cur is None or len(j.description) > len(cur.description):
            best[j.id] = j
    return list(best.values())
