"""Digest email rendering (HTML with inline styles so Gmail shows it properly)."""
from __future__ import annotations

import os
from datetime import date

from jinja2 import Environment

from .models import Job

COMMUTE_LABEL = {
    "remote": "Remote",
    "near": "Near home",
    "ok": "OK commute",
    "far": "Long commute",
    "benchmark_area": "Durham area (same move as OPM)",
    "relocation": "Relocation",
}
BENCH_LABEL = {"better": "Better than OPM", "similar": "Similar to OPM",
               "worse": "Weaker than OPM", "unclear": ""}

TEMPLATE = """\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:0 auto;color:#1f2933">
  <h2 style="margin:0 0 4px">Job matches for {{ today }}</h2>
  <p style="margin:0 0 16px;color:#52606d;font-size:14px">
    {{ jobs|length }} new match{{ '' if jobs|length == 1 else 'es' }} picked from {{ total }} postings.
    {% if tailor_url %}Want a tailored resume and cover letter? Copy the job's ID and
    <a href="{{ tailor_url }}">run "Tailor application"</a>.{% endif %}
  </p>
  {% for j in jobs %}
  <div style="border:1px solid #d9e2ec;border-radius:8px;padding:14px 16px;margin:0 0 12px">
    <div style="font-size:12px;color:#52606d;margin-bottom:4px">
      <span style="background:{{ color(j.final_score) }};color:#fff;border-radius:10px;padding:2px 8px;font-weight:bold">{{ j.final_score }}</span>
      &nbsp;{{ commute[j.commute] }}{% if j.salary_text() %} &middot; {{ j.salary_text() }}{% elif j.extra.get('salary_text') %} &middot; {{ j.extra.salary_text }}{% endif %}
      {% if j.extra.get('grade') %} &middot; {{ j.extra.grade }}{% endif %}
      {% if j.ai and bench[j.ai.vs_benchmark] %} &middot; <b>{{ bench[j.ai.vs_benchmark] }}</b>{% endif %}
    </div>
    <div style="font-size:16px;font-weight:bold"><a href="{{ j.url }}" style="color:#0b5cad;text-decoration:none">{{ j.title }}</a></div>
    <div style="font-size:14px;color:#3e4c59">{{ j.company }} &mdash; {{ j.location }}</div>
    {% if j.ai %}
    <p style="font-size:14px;margin:8px 0 4px">{{ j.ai.summary }}</p>
    {% if j.ai.concerns %}<p style="font-size:13px;margin:4px 0;color:#8a4b08">Watch: {{ j.ai.concerns }}</p>{% endif %}
    {% if j.ai.vs_benchmark_reason %}<p style="font-size:13px;margin:4px 0;color:#3e4c59">vs OPM: {{ j.ai.vs_benchmark_reason }}</p>{% endif %}
    {% if j.ai.lead_with %}<p style="font-size:13px;margin:4px 0;color:#3e4c59">Lead with: {{ j.ai.lead_with }}</p>{% endif %}
    {% else %}
    <p style="font-size:13px;margin:8px 0 4px;color:#3e4c59">{{ j.reasons|join('; ') }}</p>
    {% endif %}
    <div style="font-size:11px;color:#9aa5b1;margin-top:6px">ID {{ j.id }} &middot; via {{ j.source }}{% if j.posted %} &middot; posted {{ j.posted }}{% endif %}{% if j.extra.get('closes') %} &middot; closes {{ j.extra.closes }}{% endif %}</div>
  </div>
  {% else %}
  <p>No new matches today. The search ran fine; nothing new cleared the bar.</p>
  {% endfor %}
  <p style="font-size:11px;color:#9aa5b1;margin-top:20px">
    Sources: {% for name, msg in status.items() %}{{ name }}: {{ msg }}{{ '; ' if not loop.last }}{% endfor %}
  </p>
</div>
"""


def _color(score: int) -> str:
    return "#2f8132" if score >= 75 else "#b7791f" if score >= 55 else "#7b8794"


def tailor_url() -> str:
    repo = os.getenv("GITHUB_REPOSITORY")
    return f"https://github.com/{repo}/actions/workflows/tailor.yml" if repo else ""


def digest_html(jobs: list[Job], total: int, status: dict[str, str], today: date | None = None) -> str:
    env = Environment(autoescape=True)
    return env.from_string(TEMPLATE).render(
        jobs=jobs, total=total, status=status, today=(today or date.today()).strftime("%a %b %-d"),
        commute=COMMUTE_LABEL, bench=BENCH_LABEL, color=_color, tailor_url=tailor_url(),
    )


def digest_text(jobs: list[Job]) -> str:
    lines = []
    for j in jobs:
        lines.append(f"[{j.final_score}] {j.title} - {j.company} ({COMMUTE_LABEL.get(j.commute, '')})")
        if j.ai:
            lines.append(f"    {j.ai['summary']}")
        lines.append(f"    {j.url}   (ID {j.id})")
    return "\n".join(lines) or "No new matches today."
