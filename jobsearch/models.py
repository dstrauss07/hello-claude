from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field


@dataclass
class Job:
    source: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    posted: str = ""            # ISO date
    remote: bool | None = None  # True when the source says it is remote
    workplace: str = ""         # "remote" | "hybrid" | "onsite" | "" (unknown)
    extra: dict = field(default_factory=dict)

    # Filled in by scoring
    rule_score: int = 0
    reasons: list[str] = field(default_factory=list)
    commute: str = ""           # remote | near | ok | far | benchmark_area | relocation
    ai: dict | None = None

    @property
    def id(self) -> str:
        key = f"{_norm(self.title)}|{_norm(self.company)}"
        return hashlib.sha1(key.encode()).hexdigest()[:10]

    @property
    def final_score(self) -> int:
        if self.ai and isinstance(self.ai.get("fit_score"), int):
            # Claude's fit judgement dominates; the rule score carries the
            # location/family preferences it was told about anyway.
            return round(0.7 * self.ai["fit_score"] + 0.3 * self.rule_score)
        return self.rule_score

    def salary_text(self) -> str:
        lo, hi = self.salary_min, self.salary_max
        if lo and hi and lo != hi:
            return f"${lo:,.0f} - ${hi:,.0f}"
        if lo or hi:
            return f"${(lo or hi):,.0f}"
        return ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def strip_html(html: str) -> str:
    import html as html_lib

    text = html_lib.unescape(html or "")
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()
