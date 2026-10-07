"""Loading raw extracts efficiently and caching the cleaned result as Parquet."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from . import config
from .cleaning import CORE_STEPS, _snake
from .pipeline import CleaningPipeline


def load_raw(path: str | Path) -> pd.DataFrame:
    """Read only the needed columns, all as strings (types are fixed by the pipeline).

    Reading everything as ``string`` avoids pandas' expensive per-column type
    inference and mixed-type warnings on a large file.
    """
    header = pd.read_csv(path, nrows=0).columns
    wanted = [c for c in header if config.COLUMN_ALIASES.get(_snake(c), _snake(c)) in config.KEEP_COLUMNS]
    return pd.read_csv(path, usecols=wanted, dtype="string", engine="pyarrow")


def _fingerprint(path: Path) -> str:
    st = path.stat()
    return hashlib.md5(f"{path.name}-{st.st_size}-{st.st_mtime_ns}".encode()).hexdigest()[:10]


def load_clean(raw_path: str | Path, cache_dir: str | Path = "data/processed",
               steps=None, use_cache: bool = True) -> tuple[pd.DataFrame, CleaningPipeline | None]:
    """Return the cleaned dataset, re-using a Parquet cache when the raw file is unchanged."""
    raw_path, cache_dir = Path(raw_path), Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"crime_clean_{_fingerprint(raw_path)}.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache), None
    pipe = CleaningPipeline(steps or CORE_STEPS)
    df = pipe.run(load_raw(raw_path))
    df.to_parquet(cache, index=False)
    return df, pipe
