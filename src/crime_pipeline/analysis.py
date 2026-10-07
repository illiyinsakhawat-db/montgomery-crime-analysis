"""Reusable EDA aggregations (kept separate from plotting so they can be tested)."""
from __future__ import annotations

import pandas as pd

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def timed(df: pd.DataFrame) -> pd.DataFrame:
    """Rows whose start time is a real clock time (drops 00:00:00 / 12:00:00 'time unknown' defaults)."""
    return df[~df["time_placeholder"]]


def hourly_profile(df: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """Share of incidents in each hour of the day (optionally per group)."""
    d = timed(df)
    if by is None:
        counts = d.groupby("hour").size()
        return pd.DataFrame({"incidents": counts, "share": counts / counts.sum()})
    counts = d.groupby([by, "hour"], observed=True).size().rename("incidents").reset_index()
    counts["share"] = counts["incidents"] / counts.groupby(by, observed=True)["incidents"].transform("sum")
    return counts


def day_hour_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Incidents per (day of week, hour) – the classic heat-map input."""
    d = timed(df)
    m = d.pivot_table(index="day_name", columns="hour", values="start_datetime", aggfunc="count",
                      observed=True).reindex(DAY_ORDER)
    return m.fillna(0).astype(int)


def peak_hours(df: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    prof = hourly_profile(df)
    return prof.sort_values("incidents", ascending=False).head(n)


def hotspot_cells(df: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Densest grid cells with their most common city and block address."""
    d = df[df["has_valid_coords"]]
    cells = (d.groupby("grid_id")
               .agg(incidents=("grid_id", "size"),
                    lat=("grid_lat", "first"),
                    lon=("grid_lon", "first"))
               .sort_values("incidents", ascending=False))
    total = len(d)
    cells["share_of_county"] = cells["incidents"] / total
    cells["cumulative_share"] = cells["share_of_county"].cumsum()
    top_cells = cells.head(top).copy()
    sub = d[d["grid_id"].isin(top_cells.index)]
    mode = lambda s: s.mode().iat[0] if not s.mode().empty else pd.NA  # noqa: E731
    labels = sub.groupby("grid_id").agg(city=("city", mode), top_block=("block_address", mode),
                                        top_category=("crime_category", mode))
    return top_cells.join(labels)


def concentration(df: pd.DataFrame, pct_cells: float = 0.05) -> float:
    """Share of geocoded incidents that fall in the densest `pct_cells` of occupied grid cells."""
    counts = df[df["has_valid_coords"]].groupby("grid_id").size().sort_values(ascending=False)
    k = max(1, int(round(len(counts) * pct_cells)))
    return counts.head(k).sum() / counts.sum()


def district_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("district", observed=True)
    out = pd.DataFrame({
        "incidents": g.size(),
        "crimes_against_person_pct": g["crime_against"].apply(
            lambda s: (s.astype("string").str.contains("Person", case=False, na=False)).mean() * 100),
    })
    out["share_pct"] = out["incidents"] / out["incidents"].sum() * 100
    return out.sort_values("incidents", ascending=False).round(1)


def top_categories(df: pd.DataFrame, n: int = 10) -> pd.Series:
    return df["crime_category"].value_counts().head(n)
