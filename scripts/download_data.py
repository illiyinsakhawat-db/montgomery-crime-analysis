"""
Download the Montgomery County, MD "Crime" dataset (Open Data portal, id icn6-v9z3).

Usage:
    python scripts/download_data.py            # -> data/raw/Crime.csv

If your network blocks the request, open the URL below in a browser and save
the file as data/raw/Crime.csv.
"""
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from crime_pipeline.config import SOURCE_URL  # noqa: E402

out = ROOT / "data" / "raw" / "Crime.csv"
out.parent.mkdir(parents=True, exist_ok=True)
print(f"Downloading {SOURCE_URL}\n -> {out}")


def progress(blocks, block_size, total):
    done = blocks * block_size / 1e6
    print(f"\r  {done:,.0f} MB", end="", flush=True)


urllib.request.urlretrieve(SOURCE_URL, out, reporthook=progress)
print(f"\nDone: {out.stat().st_size / 1e6:,.0f} MB")
