"""CLI.

  python -m jobsearch digest [--dry-run] [--no-ai] [--fixture FILE]
  python -m jobsearch tailor JOB_ID_OR_URL [--dry-run]
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import requests
import yaml

from . import emailer, filters, render, sources
from .models import Job, strip_html
from .store import Store

log = logging.getLogger("jobsearch")
OUT = Path("out")


def load_config(path: str = "config.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())


def load_resume() -> str:
    text = os.getenv("RESUME_TEXT", "").strip()
    if text:
        return text
    p = Path(os.getenv("RESUME_PATH", "private/resume.md"))
    if p.exists():
        return p.read_text()
    sys.exit("No resume found: set RESUME_TEXT or put it at private/resume.md")


def cmd_digest(args, cfg: dict) -> None:
    if args.fixture:
        jobs = [Job.from_dict(d) for d in json.loads(Path(args.fixture).read_text())]
        status = {"fixture": f"{len(jobs)} postings"}
    else:
        jobs, status = sources.fetch_all(cfg)
    total = len(jobs)

    store = Store()
    scored = [j for j in (filters.score(j, cfg) for j in filters.dedupe(jobs)) if j]
    fresh = [j for j in scored if not store.seen(j.id)]
    fresh.sort(key=lambda j: j.rule_score, reverse=True)
    log.info("%d postings -> %d relevant -> %d new", total, len(scored), len(fresh))

    top = fresh[: cfg["digest"]["ai_review_limit"]]
    # Claude scoring is the only paid step; without a key the digest is free and rule-based.
    use_ai = bool(top) and not args.no_ai and bool(os.getenv("ANTHROPIC_API_KEY"))
    if use_ai:
        from . import ai  # imported lazily so --no-ai works without the SDK
        ai.score_jobs(top, load_resume(), cfg)
    else:
        log.info("Claude scoring off (no ANTHROPIC_API_KEY or --no-ai): rule-based ranking only")
    top.sort(key=lambda j: j.final_score, reverse=True)
    picks = [j for j in top if not (j.ai and j.ai["fit_score"] < 40)][: cfg["digest"]["email_top"]]

    page = render.digest_html(picks, total, status)
    OUT.mkdir(exist_ok=True)
    (OUT / "digest.html").write_text(page)
    subject = f"{len(picks)} new job match{'es' if len(picks) != 1 else ''} ({date.today():%b %-d})"

    if args.dry_run:
        print(render.digest_text(picks))
        print(f"\nWrote {OUT / 'digest.html'} (dry run: no email, state unchanged)")
        return
    if emailer.send(subject, page, render.digest_text(picks)):
        log.info("Emailed digest to %d recipient(s)", len(emailer.recipients()))
    else:
        log.warning("SMTP not configured; digest saved to %s only", OUT / "digest.html")
    # With Claude: remember everything it reviewed so it isn't re-scored tomorrow.
    # Without: remember only what was emailed, so the rest can surface later.
    store.add(top if use_ai else picks)
    store.save()


def cmd_tailor(args, cfg: dict) -> None:
    from . import ai

    job = Store().get(args.job)
    if job is None and args.job.startswith("http"):
        r = requests.get(args.job, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        job = Job(source="url", title="(from link)", company="", location="", url=args.job,
                  description=strip_html(r.text)[:20000])
    if job is None:
        sys.exit(f"Unknown job {args.job!r}: use an ID from a digest email or a posting URL")

    kit = ai.application_kit(job, load_resume(), cfg)
    OUT.mkdir(exist_ok=True)
    slug = f"{job.company}-{job.title}"[:60].replace("/", "-").replace(" ", "-")
    path = OUT / f"kit-{slug}.md"
    path.write_text(kit)
    print(kit)
    if args.dry_run:
        return
    body = f'<div style="font-family:Arial,sans-serif;white-space:pre-wrap;max-width:720px">{html.escape(kit)}</div>'
    if emailer.send(f"Application kit: {job.title} - {job.company}".strip(" -"), body, kit, {path.name: kit}):
        log.info("Emailed application kit")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="jobsearch")
    p.add_argument("--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("digest", help="fetch, score and email today's matches")
    d.add_argument("--dry-run", action="store_true", help="print instead of emailing; don't update state")
    d.add_argument("--no-ai", action="store_true", help="rule-based scoring only")
    d.add_argument("--fixture", help="read postings from a JSON file instead of the APIs")
    t = sub.add_parser("tailor", help="draft a resume/cover-letter kit for one job")
    t.add_argument("job", help="job ID from the digest, or a posting URL")
    t.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    {"digest": cmd_digest, "tailor": cmd_tailor}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
