"""
A small, reusable cleaning-pipeline framework.

Each cleaning step is a plain function ``df -> df``. Steps are chained in a
``CleaningPipeline`` that times every step, records rows in/out, and produces a
data-quality report. The same pipeline object can be re-run on any new extract.

    pipe = CleaningPipeline([standardize_columns, parse_datetimes, ...])
    clean = pipe.run(raw_df)
    print(pipe.report_frame())
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

log = logging.getLogger("crime_pipeline")

Step = Callable[[pd.DataFrame], pd.DataFrame]


@dataclass
class StepResult:
    step: str
    rows_in: int
    rows_out: int
    seconds: float
    note: str = ""

    @property
    def rows_removed(self) -> int:
        return self.rows_in - self.rows_out


@dataclass
class CleaningPipeline:
    steps: list[Step]
    name: str = "crime-cleaning"
    results: list[StepResult] = field(default_factory=list)

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        self.results = []
        for step in self.steps:
            rows_in = len(df)
            t0 = time.perf_counter()
            df = step(df)
            elapsed = time.perf_counter() - t0
            note = df.attrs.pop("_step_note", "")
            self.results.append(StepResult(step.__name__, rows_in, len(df), elapsed, note))
            log.info("%-28s %9d -> %9d rows  %6.2fs  %s", step.__name__, rows_in, len(df), elapsed, note)
        return df

    # ------------------------------------------------------------------ reporting
    def report_frame(self) -> pd.DataFrame:
        rows = [{**asdict(r), "rows_removed": r.rows_removed} for r in self.results]
        return pd.DataFrame(rows)

    def total_seconds(self) -> float:
        return sum(r.seconds for r in self.results)

    def save_report(self, path: str | Path, extra: dict | None = None) -> None:
        payload = {
            "pipeline": self.name,
            "total_seconds": round(self.total_seconds(), 3),
            "steps": [{**asdict(r), "rows_removed": r.rows_removed} for r in self.results],
        }
        if extra:
            payload.update(extra)
        Path(path).write_text(json.dumps(payload, indent=2, default=str))


def note(df: pd.DataFrame, message: str) -> pd.DataFrame:
    """Attach a short human-readable note to the current step's report line."""
    df.attrs["_step_note"] = message
    return df


def compose(*pipelines: Iterable[Step]) -> list[Step]:
    """Combine step lists, e.g. compose(CORE_STEPS, [my_custom_step])."""
    out: list[Step] = []
    for p in pipelines:
        out.extend(p)
    return out
