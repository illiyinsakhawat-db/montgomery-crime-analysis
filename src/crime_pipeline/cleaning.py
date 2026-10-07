"""
Cleaning steps for the Montgomery County crime extract.

Every function takes and returns a DataFrame, is vectorised (no row-wise
``apply``), and is safe to re-run on already-clean data (idempotent).
"""
from __future__ import annotations

import difflib
import re

import numpy as np
import pandas as pd

from . import config
from .pipeline import note


# ---------------------------------------------------------------------- helpers
def _snake(col: str) -> str:
    col = col.strip().lower()
    col = re.sub(r"[^0-9a-z]+", "_", col)
    return col.strip("_")


def _parse_dt(series: pd.Series) -> pd.Series:
    """Try each known format in turn (fast, vectorised); fall back to inference."""
    s = series.astype("string").str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    remaining = s.notna()
    for fmt in config.DATETIME_FORMATS:
        if not remaining.any():
            break
        parsed = pd.to_datetime(s[remaining], format=fmt, errors="coerce")
        out.loc[parsed.index] = out.loc[parsed.index].fillna(parsed)
        remaining = out.isna() & s.notna()
    if remaining.any():  # last resort for odd rows only
        out.loc[remaining] = pd.to_datetime(s[remaining], errors="coerce")
    return out


# ---------------------------------------------------------------------- steps
def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """snake_case headers and map known aliases to canonical names."""
    renamed = {c: config.COLUMN_ALIASES.get(_snake(c), _snake(c)) for c in df.columns}
    df = df.rename(columns=renamed)
    df = df.loc[:, ~df.columns.duplicated()]
    keep = [c for c in config.KEEP_COLUMNS if c in df.columns]
    missing = sorted(set(config.KEEP_COLUMNS) - set(keep))
    df = df[keep].copy()
    return note(df, f"kept {len(keep)} cols" + (f"; missing: {', '.join(missing)}" if missing else ""))


def drop_exact_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove fully duplicated rows (re-published records)."""
    before = len(df)
    df = df.drop_duplicates()
    return note(df, f"{before - len(df):,} exact duplicates")


def parse_datetimes(df: pd.DataFrame) -> pd.DataFrame:
    """Parse date columns with explicit formats (10-50x faster than inference)."""
    for col in ("dispatch_datetime", "start_datetime", "end_datetime"):
        if col in df.columns:
            df[col] = _parse_dt(df[col])
    bad = int(df["start_datetime"].isna().sum()) if "start_datetime" in df else 0
    return note(df, f"{bad:,} unparseable start dates")


def drop_missing_start(df: pd.DataFrame) -> pd.DataFrame:
    """An incident without a start time can't be used for time analysis."""
    before = len(df)
    df = df[df["start_datetime"].notna()]
    return note(df, f"{before - len(df):,} rows without start date")


def fix_time_order(df: pd.DataFrame) -> pd.DataFrame:
    """If end < start the two were swapped at entry; swap them back."""
    if "end_datetime" not in df:
        return df
    swap = df["end_datetime"].notna() & (df["end_datetime"] < df["start_datetime"])
    df.loc[swap, ["start_datetime", "end_datetime"]] = df.loc[swap, ["end_datetime", "start_datetime"]].to_numpy()
    return note(df, f"{int(swap.sum()):,} start/end swapped")


def clean_text_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace, unify case, fix known city misspellings, blank -> NA."""
    text_cols = [c for c in ("crime_against", "crime_category", "crime_detail", "district",
                             "block_address", "city", "agency", "place", "sector", "beat")
                 if c in df.columns]
    for c in text_cols:
        s = df[c].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        df[c] = s.replace({"": pd.NA, "NULL": pd.NA, "N/A": pd.NA})
    if "city" in df:
        df["city"] = df["city"].str.upper().str.replace(r"\s*#\d+$", "", regex=True).replace(config.CITY_FIXES)
    if "district" in df:
        df["district"] = df["district"].str.upper()
    if "block_address" in df:
        df["block_address"] = df["block_address"].str.upper()
    return note(df, f"{len(text_cols)} text cols normalised")


def build_city_map(values, canonical=None, cutoff=None) -> dict:
    """Map each distinct raw city to its closest canonical name (or NA if no good match).

    Matching runs once per *distinct* value (a few hundred), not per row, so it
    stays fast on 500k+ rows and adapts automatically to new misspellings.
    """
    canonical = canonical or config.CANONICAL_CITIES
    cutoff = cutoff or config.CITY_MATCH_CUTOFF
    mapping = {}
    for v in values:
        if v in canonical:
            mapping[v] = v
            continue
        hit = difflib.get_close_matches(v, canonical, n=1, cutoff=cutoff)
        mapping[v] = hit[0] if hit else pd.NA
    return mapping


def standardize_cities(df: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy-match misspelt city names (e.g. 'SILVER SRING') to canonical names."""
    if "city" not in df:
        return df
    distinct = df["city"].dropna().unique().tolist()
    mapping = build_city_map(distinct)
    fixed = sum(1 for k, v in mapping.items() if pd.notna(v) and k != v)
    unmatched = sum(1 for v in mapping.values() if pd.isna(v))
    df["city"] = df["city"].map(mapping).astype("string")
    return note(df, f"{len(distinct)} distinct -> {df['city'].nunique()} cities; {fixed} variants fixed, "
                    f"{unmatched} unmatched -> NA")


def flag_non_crimes(df: pd.DataFrame) -> pd.DataFrame:
    """NIBRS 'Crime Against Not a Crime' records (e.g. lost property) are kept but flagged."""
    s = df["crime_against"].astype("string").str.lower()
    df["is_crime"] = ~s.str.contains("not a crime", na=False)
    return note(df, f"{int((~df['is_crime']).sum()):,} non-crime records flagged")


def clean_zip_codes(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the 5-digit ZIP only; anything invalid becomes NA."""
    if "zip_code" not in df:
        return df
    z = df["zip_code"].astype("string").str.extract(r"(\d{5})", expand=False)
    invalid = int(df["zip_code"].notna().sum() - z.notna().sum())
    df["zip_code"] = z
    return note(df, f"{invalid:,} invalid ZIPs nulled")


def validate_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """Null out coordinates that are 0/missing or fall outside the county."""
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    ok = lat.between(*config.LAT_RANGE) & lon.between(*config.LON_RANGE)
    df["latitude"] = lat.where(ok).astype("float32")
    df["longitude"] = lon.where(ok).astype("float32")
    df["has_valid_coords"] = ok
    return note(df, f"{int((~ok).sum()):,} rows with invalid/missing coords")


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    if "victims" in df:
        df["victims"] = pd.to_numeric(df["victims"], errors="coerce").astype("Int16")
    if "incident_id" in df:
        df["incident_id"] = pd.to_numeric(df["incident_id"], errors="coerce").astype("Int64")
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive the calendar/clock features used throughout the EDA."""
    s = df["start_datetime"]
    df["year"] = s.dt.year.astype("int16")
    df["month"] = s.dt.month.astype("int8")
    df["year_month"] = s.dt.to_period("M").dt.to_timestamp()
    df["day_of_week"] = s.dt.dayofweek.astype("int8")          # Monday = 0
    df["day_name"] = s.dt.day_name()
    df["hour"] = s.dt.hour.astype("int8")
    df["is_weekend"] = df["day_of_week"] >= 5
    bins = [b[0] for b in config.TIME_BANDS] + [24]
    labels = [b[2] for b in config.TIME_BANDS]
    df["time_band"] = pd.cut(df["hour"], bins=bins, labels=labels, right=False)
    # Start times of exactly 00:00:00 or 12:00:00 are used as "time unknown" defaults
    # (12:00:00 occurs ~2x as often as any other exact hour) -> flag, exclude from clock analysis
    exact = (s.dt.minute == 0) & (s.dt.second == 0)
    df["time_placeholder"] = exact & s.dt.hour.isin([0, 12])
    if "dispatch_datetime" in df:
        lag = (df["dispatch_datetime"] - s).dt.total_seconds() / 3600
        df["report_lag_hours"] = lag.where(lag >= 0).astype("float32")
    return note(df, "year, month, dow, hour, time_band, report lag")


def add_hotspot_cell(df: pd.DataFrame) -> pd.DataFrame:
    """Snap coordinates to a fixed grid so incidents can be counted per cell."""
    g = config.HOTSPOT_GRID_DEG
    df["grid_lat"] = (np.floor(df["latitude"] / g) * g + g / 2).round(4)
    df["grid_lon"] = (np.floor(df["longitude"] / g) * g + g / 2).round(4)
    df["grid_id"] = (df["grid_lat"].astype("string") + "," + df["grid_lon"].astype("string")).where(
        df["has_valid_coords"])
    return note(df, f"grid {g}°")


def optimise_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Convert low-cardinality text to 'category' to cut memory use."""
    before = df.memory_usage(deep=True).sum()
    for c in config.CATEGORICAL_COLUMNS:
        if c in df.columns:
            df[c] = df[c].astype("category")
    after = df.memory_usage(deep=True).sum()
    return note(df, f"memory {before / 1e6:,.0f} MB -> {after / 1e6:,.0f} MB")


# Default, ordered step list – reuse as-is or extend with compose()
CORE_STEPS = [
    standardize_columns,
    drop_exact_duplicates,
    parse_datetimes,
    drop_missing_start,
    fix_time_order,
    clean_text_fields,
    standardize_cities,
    flag_non_crimes,
    clean_zip_codes,
    validate_coordinates,
    coerce_numeric,
    add_time_features,
    add_hotspot_cell,
    optimise_dtypes,
]
