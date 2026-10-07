"""
Clean a raw Montgomery County crime extract and write a Parquet file + quality report.

Usage:
    python scripts/run_pipeline.py data/raw/Crime.csv
    python scripts/run_pipeline.py data/raw/Crime.csv --out data/processed/crime_clean.parquet
"""
import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crime_pipeline import CORE_STEPS, CleaningPipeline, load_raw  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw_csv")
    ap.add_argument("--out", default=str(ROOT / "data" / "processed" / "crime_clean.parquet"))
    ap.add_argument("--report", default=str(ROOT / "reports" / "data_quality_report.json"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raw = load_raw(args.raw_csv)
    pipe = CleaningPipeline(CORE_STEPS)
    clean = pipe.run(raw)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(args.out, index=False)
    pipe.save_report(args.report, extra={
        "source_file": Path(args.raw_csv).name,
        "rows_raw": len(raw),
        "rows_clean": len(clean),
        "date_range": [str(clean["start_datetime"].min()), str(clean["start_datetime"].max())],
        "pct_with_valid_coords": round(100 * clean["has_valid_coords"].mean(), 1),
        "pct_time_placeholder": round(100 * clean["time_placeholder"].mean(), 1),
    })
    print(f"\n{len(raw):,} raw rows -> {len(clean):,} clean rows in {pipe.total_seconds():.1f}s")
    print(f"Saved {args.out}\nReport {args.report}")


if __name__ == "__main__":
    main()
