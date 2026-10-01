import json
from types import SimpleNamespace as NS

import yaml

from jobsearch import ai
from jobsearch.models import Job
from tests.test_pipeline import ROOT


class FakeMessages:
    def __init__(self, reply, stop_reason="end_turn"):
        self.reply, self.stop_reason, self.calls = reply, stop_reason, []

    def create(self, **kw):
        self.calls.append(kw)
        text = self.reply(kw) if callable(self.reply) else self.reply
        return NS(stop_reason=self.stop_reason, stop_details=None,
                  content=[NS(type="thinking", thinking=""), NS(type="text", text=text)])


def client(msgs):
    return NS(beta=NS(messages=msgs))


def cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def make_jobs(n):
    return [Job(source="t", title=f"OD Specialist {i}", company="Co", location="Remote", url=f"u{i}",
                description="x" * 10000, commute="remote") for i in range(n)]


def test_score_jobs_batches_and_parses():
    jobs = make_jobs(10)

    def reply(kw):
        ids = [line.split('"')[1] for line in kw["messages"][0]["content"].splitlines() if line.startswith("<job id=")]
        return json.dumps({"jobs": [{"id": i, "fit_score": 150, "summary": "s", "concerns": "",
                                     "vs_benchmark": "better", "vs_benchmark_reason": "r",
                                     "lead_with": "PMP"} for i in ids]})

    msgs = FakeMessages(reply)
    ai.score_jobs(jobs, "RESUME", cfg(), client=client(msgs))
    assert len(msgs.calls) == 2  # 8 + 2
    call = msgs.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "RESUME" in call["system"] and "x" * (ai.DESC_CHARS + 1) not in call["messages"][0]["content"]
    assert all(j.ai and j.ai["fit_score"] == 100 for j in jobs)  # clamped


def test_refusal_leaves_jobs_unscored():
    jobs = make_jobs(2)
    ai.score_jobs(jobs, "R", cfg(), client=client(FakeMessages("", stop_reason="refusal")))
    assert all(j.ai is None for j in jobs)


def test_application_kit_returns_text():
    msgs = FakeMessages("## Kit")
    out = ai.application_kit(make_jobs(1)[0], "R", cfg(), client=client(msgs))
    assert out == "## Kit" and "Never invent" in msgs.calls[0]["messages"][0]["content"]
