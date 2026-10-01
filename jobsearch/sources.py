"""Job sources. Each fetcher returns a list[Job] and never raises: a source that
is unconfigured or down is logged and skipped so the digest still goes out."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import requests

from .models import Job, strip_html

log = logging.getLogger(__name__)
TIMEOUT = 30


def fetch_all(cfg: dict) -> tuple[list[Job], dict[str, str]]:
    """Returns (jobs, status) where status maps source name -> short message."""
    jobs: list[Job] = []
    status: dict[str, str] = {}
    for name, fn in [
        ("USAJobs", fetch_usajobs),
        ("Adzuna", fetch_adzuna),
        ("Remotive", fetch_remotive),
        ("Greenhouse", fetch_greenhouse),
        ("Lever", fetch_lever),
    ]:
        try:
            found, msg = fn(cfg)
        except Exception as e:  # keep the digest alive if one source breaks
            log.exception("%s failed", name)
            found, msg = [], f"error: {e.__class__.__name__}: {e}"
        jobs.extend(found)
        status[name] = msg
        log.info("%s: %s", name, msg)
    return jobs, status


# --- USAJobs (federal) -------------------------------------------------------
# Free key: https://developer.usajobs.gov/apirequest/
def fetch_usajobs(cfg: dict) -> tuple[list[Job], str]:
    key, email = os.getenv("USAJOBS_API_KEY"), os.getenv("USAJOBS_EMAIL")
    if not (key and email):
        return [], "skipped (USAJOBS_API_KEY / USAJOBS_EMAIL not set)"
    headers = {"Host": "data.usajobs.gov", "User-Agent": email, "Authorization-Key": key}
    s = cfg["searches"]
    u = s.get("usajobs", {})
    days = min(int(s.get("max_days_old", 7)), 60)
    queries = []
    # Remote anywhere, plus anything within commuting distance of home.
    for code in u.get("job_category_codes", []):
        queries.append({"JobCategoryCode": code, "RemoteIndicator": "True"})
        queries.append({"JobCategoryCode": code, "LocationName": cfg["location"]["adzuna_where"], "Radius": 40})
    queries.append({"Keyword": "organizational psychologist", "RemoteIndicator": "True"})
    queries.append({"Keyword": "organizational development"})

    jobs: dict[str, Job] = {}
    for q in queries:
        params = {"ResultsPerPage": 250, "DatePosted": days, **q}
        if u.get("public_only", True):
            params["HiringPath"] = "public"
        r = requests.get("https://data.usajobs.gov/api/search", params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        for item in r.json().get("SearchResult", {}).get("SearchResultItems", []):
            j = _usajobs_item(item.get("MatchedObjectDescriptor", {}))
            if j:
                jobs[j.url] = j
    return list(jobs.values()), f"{len(jobs)} postings"


def _usajobs_item(d: dict) -> Job | None:
    if not d:
        return None
    details = (d.get("UserArea") or {}).get("Details") or {}
    pay = (d.get("PositionRemuneration") or [{}])[0]
    remote = bool(details.get("RemoteIndicator"))
    telework = bool(details.get("TeleworkEligible"))
    desc = "\n\n".join(filter(None, [
        details.get("JobSummary", ""),
        d.get("QualificationSummary", ""),
        " ".join(details.get("MajorDuties") or []) if isinstance(details.get("MajorDuties"), list) else details.get("MajorDuties", ""),
    ]))
    grade = ""
    if details.get("LowGrade"):
        grade = f"GS-{details.get('LowGrade')}" + (f"/{details.get('HighGrade')}" if details.get("HighGrade") not in (None, details.get("LowGrade")) else "")
    return Job(
        source="USAJobs",
        title=d.get("PositionTitle", ""),
        company=d.get("OrganizationName") or d.get("DepartmentName", ""),
        location=d.get("PositionLocationDisplay", ""),
        url=d.get("PositionURI", ""),
        description=strip_html(desc),
        salary_min=_num(pay.get("MinimumRange")) if pay.get("RateIntervalCode", "PA") == "PA" else None,
        salary_max=_num(pay.get("MaximumRange")) if pay.get("RateIntervalCode", "PA") == "PA" else None,
        posted=(d.get("PublicationStartDate") or "")[:10],
        remote=remote,
        workplace="remote" if remote else ("hybrid" if telework else ""),
        extra={"grade": grade, "closes": (d.get("ApplicationCloseDate") or "")[:10],
               "telework": telework},
    )


# --- Adzuna (aggregates Indeed/Glassdoor/company sites) ----------------------
# Free key: https://developer.adzuna.com/signup
def fetch_adzuna(cfg: dict) -> tuple[list[Job], str]:
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return [], "skipped (ADZUNA_APP_ID / ADZUNA_APP_KEY not set)"
    s, loc = cfg["searches"], cfg["location"]
    jobs: dict[str, Job] = {}
    for kw in s["keywords"]:
        # Local search, then a nationwide "remote" search for the same keyword.
        for where, what in [(loc["adzuna_where"], kw), (None, f"{kw} remote")]:
            params = {
                "app_id": app_id, "app_key": app_key, "what": what,
                "results_per_page": 50, "max_days_old": s.get("max_days_old", 7),
                "content-type": "application/json",
            }
            if where:
                params.update(where=where, distance=loc.get("adzuna_radius_km", 50))
            r = requests.get("https://api.adzuna.com/v1/api/jobs/us/search/1", params=params, timeout=TIMEOUT)
            if r.status_code == 429:
                time.sleep(5)
                continue
            r.raise_for_status()
            for d in r.json().get("results", []):
                j = Job(
                    source="Adzuna",
                    title=strip_html(d.get("title", "")),
                    company=(d.get("company") or {}).get("display_name", ""),
                    location=(d.get("location") or {}).get("display_name", ""),
                    url=d.get("redirect_url", ""),
                    description=strip_html(d.get("description", "")),
                    salary_min=_num(d.get("salary_min")),
                    salary_max=_num(d.get("salary_max")),
                    posted=(d.get("created") or "")[:10],
                )
                jobs[j.id] = j
            time.sleep(0.5)
    return list(jobs.values()), f"{len(jobs)} postings"


# --- Remotive (remote-only board, no key) -------------------------------------
def fetch_remotive(cfg: dict) -> tuple[list[Job], str]:
    jobs: dict[str, Job] = {}
    # Remotive asks API users to keep request volume low, so one category pull
    # plus two targeted searches.
    for params in ({"category": "hr"}, {"search": "organizational"}, {"search": "people analytics"}):
        r = requests.get("https://remotive.com/api/remote-jobs", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        for d in r.json().get("jobs", []):
            j = Job(
                source="Remotive",
                title=d.get("title", ""),
                company=d.get("company_name", ""),
                location=f"Remote ({d.get('candidate_required_location') or 'anywhere'})",
                url=d.get("url", ""),
                description=strip_html(d.get("description", "")),
                posted=(d.get("publication_date") or "")[:10],
                remote=True,
                workplace="remote",
                extra={"salary_text": d.get("salary", "")},
            )
            jobs[j.id] = j
    return list(jobs.values()), f"{len(jobs)} postings"


# --- Company boards: Greenhouse & Lever (no key) -----------------------------
def fetch_greenhouse(cfg: dict) -> tuple[list[Job], str]:
    boards = cfg["searches"].get("greenhouse_boards") or []
    if not boards:
        return [], "skipped (no boards listed in config.yaml)"
    jobs = []
    for token in boards:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                         params={"content": "true"}, timeout=TIMEOUT)
        if r.status_code == 404:
            log.warning("Greenhouse board %r not found", token)
            continue
        r.raise_for_status()
        for d in r.json().get("jobs", []):
            loc = (d.get("location") or {}).get("name", "")
            jobs.append(Job(
                source="Greenhouse", title=d.get("title", ""), company=token,
                location=loc, url=d.get("absolute_url", ""),
                description=strip_html(d.get("content", "")),
                posted=(d.get("updated_at") or "")[:10],
                remote="remote" in loc.lower() or None,
            ))
    return jobs, f"{len(jobs)} postings from {len(boards)} boards"


def fetch_lever(cfg: dict) -> tuple[list[Job], str]:
    companies = cfg["searches"].get("lever_companies") or []
    if not companies:
        return [], "skipped (no companies listed in config.yaml)"
    jobs = []
    for co in companies:
        r = requests.get(f"https://api.lever.co/v0/postings/{co}", params={"mode": "json"}, timeout=TIMEOUT)
        if r.status_code == 404:
            log.warning("Lever company %r not found", co)
            continue
        r.raise_for_status()
        for d in r.json():
            cats = d.get("categories") or {}
            wt = (d.get("workplaceType") or "").lower()
            created = d.get("createdAt")
            jobs.append(Job(
                source="Lever", title=d.get("text", ""), company=co,
                location=cats.get("location", ""), url=d.get("hostedUrl", ""),
                description=d.get("descriptionPlain", ""),
                posted=datetime.fromtimestamp(created / 1000, timezone.utc).date().isoformat() if created else "",
                remote=(wt == "remote") or None,
                workplace={"remote": "remote", "hybrid": "hybrid", "on-site": "onsite", "onsite": "onsite"}.get(wt, ""),
            ))
    return jobs, f"{len(jobs)} postings from {len(companies)} companies"


def _num(v) -> float | None:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None
