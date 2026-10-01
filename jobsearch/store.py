"""Small JSON state kept between runs (restored from the GitHub Actions cache,
never committed): which jobs were already emailed, and their full details so
the tailor command can look them up by ID."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .models import Job

KEEP_DAYS = 90


class Store:
    def __init__(self, root: str | Path = "state"):
        self.root = Path(root)
        self.path = self.root / "jobs.json"
        self.data: dict[str, dict] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def seen(self, job_id: str) -> bool:
        return job_id in self.data

    def add(self, jobs: list[Job], today: date | None = None) -> None:
        today = today or date.today()
        for j in jobs:
            d = j.to_dict()
            d["sent_on"] = today.isoformat()
            self.data[j.id] = d

    def get(self, job_id: str) -> Job | None:
        d = self.data.get(job_id)
        return Job.from_dict(d) if d else None

    def save(self, today: date | None = None) -> None:
        cutoff = ((today or date.today()) - timedelta(days=KEEP_DAYS)).isoformat()
        self.data = {k: v for k, v in self.data.items() if v.get("sent_on", "") >= cutoff}
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1))
