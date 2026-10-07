"""
Benchmark: ad-hoc notebook cleaning vs. the reusable pipeline.

The "baseline" reproduces the way this data is typically cleaned in a one-off
notebook: default read_csv (full type inference, all columns), datetime parsing
without a format string, and row-wise .apply() for text/ZIP/coordinate fixes.
Both versions produce the same cleaned rows; only the engineering differs.

Usage:
    python scripts/benchmark.py data/raw/Crime.csv [--repeats 3]
Writes reports/benchmark.json and prints a summary table.
"""
import argparse
import json
import statistics
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crime_pipeline import CORE_STEPS, CleaningPipeline, load_raw  # noqa: E402
from crime_pipeline import config  # noqa: E402

warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------- baseline
def baseline_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)                                    # all columns, inferred types
    df.columns = [c.strip().lower().replace(" ", "_").replace("/", "") for c in df.columns]
    df = df.drop_duplicates()
    start_col = [c for c in df.columns if c.startswith("start")][0]
    end_col = [c for c in df.columns if c.startswith("end")][0]
    disp_col = [c for c in df.columns if c.startswith("dispatch")][0]
    for c in (start_col, end_col, disp_col):
        df[c] = pd.to_datetime(df[c], errors="coerce")       # no format -> per-row inference
    df = df[df[start_col].notna()]

    def fix_city(x):
        if pd.isna(x):
            return x
        x = " ".join(str(x).strip().split()).upper()
        return config.CITY_FIXES.get(x, x)
    df["city"] = df["city"].apply(fix_city)

    def fix_zip(z):
        z = str(z)
        digits = "".join(ch for ch in z if ch.isdigit())
        return digits[:5] if len(digits) >= 5 else np.nan
    df["zip_code"] = df["zip_code"].apply(fix_zip)

    def valid(row):
        return (config.LAT_RANGE[0] <= row["latitude"] <= config.LAT_RANGE[1]
                and config.LON_RANGE[0] <= row["longitude"] <= config.LON_RANGE[1])
    df["has_valid_coords"] = df.apply(valid, axis=1)
    df.loc[~df["has_valid_coords"], ["latitude", "longitude"]] = np.nan

    df["hour"] = df[start_col].apply(lambda t: t.hour)
    df["day_name"] = df[start_col].apply(lambda t: t.day_name())
    df["year"] = df[start_col].apply(lambda t: t.year)
    return df


# --------------------------------------------------------------------------- pipeline
def pipeline_clean(path: str) -> pd.DataFrame:
    return CleaningPipeline(CORE_STEPS).run(load_raw(path))


def timeit(fn, path, repeats):
    times, out = [], None
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn(path)
        times.append(time.perf_counter() - t0)
    return statistics.median(times), out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_csv")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    t_base, base = timeit(baseline_clean, args.raw_csv, args.repeats)
    t_pipe, pipe = timeit(pipeline_clean, args.raw_csv, args.repeats)

    # cached re-run (what an analyst experiences on the 2nd+ notebook session)
    cache_dir = ROOT / "data" / "processed"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "_benchmark_cache.parquet"
    pipe.to_parquet(cache, index=False)
    t_cache, _ = timeit(lambda p: pd.read_parquet(cache), args.raw_csv, args.repeats)
    cache.unlink()

    result = {
        "rows_raw": int(pd.read_csv(args.raw_csv, usecols=[0]).shape[0]),
        "rows_clean_baseline": len(base),
        "rows_clean_pipeline": len(pipe),
        "baseline_seconds": round(t_base, 2),
        "pipeline_seconds": round(t_pipe, 2),
        "cached_reload_seconds": round(t_cache, 2),
        "time_saved_pct_first_run": round(100 * (1 - t_pipe / t_base), 1),
        "time_saved_pct_cached": round(100 * (1 - t_cache / t_base), 1),
        "memory_mb_baseline": round(base.memory_usage(deep=True).sum() / 1e6, 1),
        "memory_mb_pipeline": round(pipe.memory_usage(deep=True).sum() / 1e6, 1),
        "repeats": args.repeats,
    }
    out = ROOT / "reports" / "benchmark.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    for k, v in result.items():
        print(f"{k:28s} {v}")


if __name__ == "__main__":
    main()
