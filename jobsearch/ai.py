"""Claude-powered fit scoring and application-kit drafting."""
from __future__ import annotations

import json
import logging
import os

import anthropic

from .models import Job

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
# Server-side fallback: if a request is declined, the API re-runs it on
# Anthropic's recommended fallback model instead of returning a refusal.
BETAS = ["server-side-fallback-2026-07-01"]
BATCH_SIZE = 8
DESC_CHARS = 4000

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "jobs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "fit_score": {"type": "integer"},
                    "summary": {"type": "string"},
                    "concerns": {"type": "string"},
                    "vs_benchmark": {"type": "string", "enum": ["better", "similar", "worse", "unclear"]},
                    "vs_benchmark_reason": {"type": "string"},
                    "lead_with": {"type": "string"},
                },
                "required": ["id", "fit_score", "summary", "concerns", "vs_benchmark",
                             "vs_benchmark_reason", "lead_with"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["jobs"],
    "additionalProperties": False,
}


def _system(resume: str, cfg: dict) -> str:
    b = cfg.get("benchmark", {})
    salary = f"${b['salary']:,}" if b.get("salary") else "not specified"
    return f"""You help a candidate with very little free time decide which jobs are worth applying to.

<candidate_resume>
{resume}
</candidate_resume>

<situation>
- Lives in {cfg['location']['home']}. {os.getenv("CANDIDATE_CONTEXT", "")}
- Strong preference: fully remote. Next best: hybrid with a short commute from home
  (East Cobb / Cumberland / Sandy Springs / Roswell). Daily commutes into Midtown or
  Downtown Atlanta are a real cost. On-site roles only if the fit is excellent.
- Relocation is possible but a cost to the family.
- Benchmark she is weighing: {b.get('label', 'n/a')} (salary: {salary}). {b.get('notes', '')}
- Family fit matters: flexibility, predictable hours, limited overnight travel.
</situation>"""


def score_jobs(jobs: list[Job], resume: str, cfg: dict, client: anthropic.Anthropic | None = None) -> None:
    """Sets job.ai in place. Jobs that fail to score keep ai=None."""
    client = client or anthropic.Anthropic()
    system = _system(resume, cfg)
    for i in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[i:i + BATCH_SIZE]
        try:
            results = _score_batch(client, system, batch)
        except anthropic.APIStatusError as e:
            log.error("Claude scoring failed (HTTP %s, request %s): %s",
                      e.status_code, e.response.headers.get("request-id"), e.message)
            continue
        except anthropic.APIConnectionError as e:
            log.error("Claude scoring connection error: %s", e)
            continue
        by_id = {r["id"]: r for r in results}
        for j in batch:
            if j.id in by_id:
                r = by_id[j.id]
                r["fit_score"] = max(0, min(100, int(r["fit_score"])))
                j.ai = r


def _score_batch(client: anthropic.Anthropic, system: str, batch: list[Job]) -> list[dict]:
    listings = []
    for j in batch:
        listings.append(
            f'<job id="{j.id}">\nTitle: {j.title}\nEmployer: {j.company}\nLocation: {j.location} '
            f"(commute class: {j.commute})\nSalary: {j.salary_text() or j.extra.get('salary_text') or 'not listed'}"
            f"{' | Grade: ' + j.extra['grade'] if j.extra.get('grade') else ''}\n"
            f"Description:\n{j.description[:DESC_CHARS]}\n</job>"
        )
    prompt = (
        "Score each job below for this candidate. fit_score is 0-100: how likely she is "
        "to be competitive AND happy in it, counting her I-O master's (2025), PMP, project "
        "and change-management track record, and the location/family situation. Treat "
        "roles needing years of post-degree I-O experience she lacks as stretches, not "
        "matches. summary: one or two sentences on why it fits. concerns: the main "
        "risk or gap, or empty string. vs_benchmark compares the whole package (pay, "
        "staying home vs moving, flexibility, career value) to the OPM offer. lead_with: "
        "which part of her background to put first in the application.\n\n"
        + "\n\n".join(listings)
    )
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=BETAS,
        fallbacks="default",
        cache_control={"type": "ephemeral"},  # resume/system prompt reused across batches
        system=system,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCORE_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        log.warning("Scoring batch declined: %s", getattr(resp.stop_details, "category", None))
        return []
    if resp.stop_reason == "max_tokens":
        log.warning("Scoring batch truncated; skipping")
        return []
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text).get("jobs", [])


def application_kit(job: Job, resume: str, cfg: dict, client: anthropic.Anthropic | None = None) -> str:
    """Markdown kit: tailored summary, resume bullets, cover letter, interview prep."""
    client = client or anthropic.Anthropic()
    prompt = f"""Draft an application kit for this job. She will review and edit before sending.

<job>
Title: {job.title}
Employer: {job.company}
Location: {job.location}
URL: {job.url}
Description:
{job.description}
</job>

Write Markdown with these sections:
1. **Fit in one line**: why she is a credible candidate.
2. **Resume summary**: a 3-4 sentence professional summary tailored to this posting.
3. **Resume bullets to use**: 6-8 bullets rewritten from her real experience, ordered
   for this job, using the posting's own vocabulary where it is accurate (this helps
   with applicant tracking systems). Note which original role each comes from.
4. **Keywords to include**: terms from the posting her resume should contain.
5. **Cover letter**: under 300 words, warm and specific, in her voice (first person),
   no clichés.
6. **Screening answers**: short drafts for "Why this role?" and "Why this organization?".
7. **Interview prep**: 5 likely questions with a STAR-story prompt drawn from her
   experience for each.
8. **Gaps to address**: honest list of requirements she doesn't clearly meet and how
   to frame them.

Never invent experience, employers, metrics or credentials that are not in her resume.
If the posting is federal (USAJobs), make sure the bullets show the specialized
experience the announcement lists, since federal HR screens on that."""
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=BETAS,
        fallbacks="default",
        system=_system(resume, cfg),
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to draft this kit.")
    return "\n".join(b.text for b in resp.content if b.type == "text").strip()
