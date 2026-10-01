import json
from pathlib import Path

import pytest
import yaml

from jobsearch import filters, render
from jobsearch.models import Job, strip_html
from jobsearch.sources import _usajobs_item
from jobsearch.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


@pytest.fixture
def jobs():
    data = json.loads((ROOT / "tests/fixtures/sample_jobs.json").read_text())
    return [Job.from_dict(d) for d in data]


def scored(jobs, cfg):
    return {j.title + "|" + j.company: j for j in (filters.score(j, cfg) for j in filters.dedupe(jobs)) if j}


def test_excludes_unrelated_and_clinical(jobs, cfg):
    titles = {k.split("|")[0] for k in scored(jobs, cfg)}
    assert "Clinical Psychologist" not in titles
    assert "Warehouse Associate" not in titles


def test_dedupe_keeps_richer_description(jobs, cfg):
    s = scored(jobs, cfg)
    cm = [j for j in s.values() if j.title == "Change Management Consultant"]
    assert len(cm) == 1 and "Hybrid role" in cm[0].description


def test_commute_classes(jobs, cfg):
    s = scored(jobs, cfg)
    by_title = {j.title: j for j in s.values()}
    assert by_title["Industrial-Organizational Psychologist"].commute == "remote"
    assert by_title["Change Management Consultant"].commute == "near"
    assert by_title["Organizational Development Specialist"].commute == "far"
    assert by_title["Talent Management Program Manager"].commute == "benchmark_area"


def test_ranking_prefers_remote_and_near_over_midtown(jobs, cfg):
    by_title = {j.title: j for j in scored(jobs, cfg).values()}
    remote = by_title["Industrial-Organizational Psychologist"].rule_score
    near = by_title["Change Management Consultant"].rule_score
    midtown = by_title["Organizational Development Specialist"].rule_score
    assert remote > midtown and near > midtown
    assert any("watch out" in r for r in by_title["Organizational Development Specialist"].reasons)


def test_word_boundaries():
    assert not filters._has("walk through the plan", "hr")
    assert filters._has("hr business partner", "hr")


def test_final_score_blends_ai(jobs):
    j = jobs[0]
    j.rule_score = 50
    assert j.final_score == 50
    j.ai = {"fit_score": 90}
    assert j.final_score == 78


def test_usajobs_parser():
    item = {
        "PositionTitle": "Personnel Research Psychologist",
        "PositionURI": "https://www.usajobs.gov/job/9",
        "OrganizationName": "Office of Personnel Management",
        "PositionLocationDisplay": "Atlanta, Georgia",
        "PositionRemuneration": [{"MinimumRange": "72553", "MaximumRange": "94317", "RateIntervalCode": "PA"}],
        "PublicationStartDate": "2026-09-30T00:00:00",
        "ApplicationCloseDate": "2026-10-10T23:59:59",
        "UserArea": {"Details": {"JobSummary": "<p>Assessment work</p>", "TeleworkEligible": True,
                                 "RemoteIndicator": False, "LowGrade": "11", "HighGrade": "12"}},
    }
    j = _usajobs_item(item)
    assert j.workplace == "hybrid" and j.salary_min == 72553 and j.extra["grade"] == "GS-11/12"
    assert j.description == "Assessment work" and j.extra["closes"] == "2026-10-10"


def test_strip_html():
    assert strip_html("<p>A &amp; B</p><ul><li>one</li></ul>") == "A & B\n one"


def test_render_escapes_and_lists(jobs, cfg):
    picks = [j for j in (filters.score(j, cfg) for j in jobs) if j][:3]
    picks[0].title = "<script>x</script>"
    picks[0].ai = {"fit_score": 80, "summary": "Strong fit", "concerns": "", "vs_benchmark": "better",
                   "vs_benchmark_reason": "Stays home", "lead_with": "PMP"}
    html = render.digest_html(picks, total=8, status={"fixture": "ok"})
    assert "&lt;script&gt;" in html and "Better than OPM" in html and picks[1].url in html


def test_store_roundtrip(tmp_path, jobs):
    s = Store(tmp_path)
    s.add(jobs[:2])
    s.save()
    s2 = Store(tmp_path)
    assert s2.seen(jobs[0].id) and s2.get(jobs[1].id).title == jobs[1].title
