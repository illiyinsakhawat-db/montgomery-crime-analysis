"""
Exploratory analysis: builds every figure in reports/figures/, an interactive
hotspot map (reports/hotspot_map.html) and reports/findings.json.

Usage:
    python scripts/make_figures.py data/processed/crime_clean.parquet
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from crime_pipeline import analysis as A  # noqa: E402

FIG = ROOT / "reports" / "figures"

# --- palette (validated categorical order + single-hue sequential ramp) ---------
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_LIGHT = "#9ec5f4"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
SEQ = LinearSegmentedColormap.from_list(
    "seq_blue", ["#f3f7fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10.5, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titleweight": "bold",
    "axes.titlesize": 13, "axes.titlelocation": "left", "axes.titlepad": 12,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.major.size": 0, "ytick.major.size": 0,
    "legend.frameon": False, "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
})


def subtitle(ax, text):
    ax.text(0, 1.02, text, transform=ax.transAxes, color=INK2, fontsize=9.5, va="bottom")


def save(fig, name):
    fig.savefig(FIG / name)
    plt.close(fig)
    print("  saved", name)


def fmt_hour(h):
    return f"{h:02d}:00"


# ================================================================== figures
def fig_monthly_trend(df, out):
    m = df.groupby("year_month").size()
    m = m[m.index < m.index.max()]                       # drop the partial latest month
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(m.index, m.values, color=BLUE, lw=2)
    roll = m.rolling(12, center=True).mean()
    ax.plot(roll.index, roll.values, color=INK2, lw=1.2, ls="--")
    ax.text(roll.dropna().index[-1], roll.dropna().iloc[-1], "  12-month avg", color=INK2, va="center", fontsize=9)
    ax.yaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
    ax.set_title("Reported incidents per month", y=1.06)
    subtitle(ax, f"Montgomery County, MD · {m.index.min():%b %Y} – {m.index.max():%b %Y}")
    ax.grid(axis="x", visible=False)
    save(fig, "01_monthly_trend.png")
    out["monthly_mean"] = int(m.mean())
    out["busiest_month"] = f"{m.idxmax():%B %Y} ({m.max():,})"
    by_year = df[df["year"] < df["year"].max()].groupby("year").size()
    out["incidents_by_full_year"] = {int(k): int(v) for k, v in by_year.items()}


def fig_hour_of_day(df, out):
    prof = A.hourly_profile(df)
    top3 = prof["incidents"].nlargest(3).index
    colors = [BLUE if h in top3 else BLUE_LIGHT for h in prof.index]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(prof.index, prof["share"] * 100, color=colors, width=0.8)
    for h in top3:
        ax.text(h, prof.loc[h, "share"] * 100 - 0.15, f"{prof.loc[h, 'share'] * 100:.1f}", ha="center", va="top",
                color="white", fontsize=8, fontweight="bold")
    ax.set_xticks(range(0, 24, 2), [fmt_hour(h) for h in range(0, 24, 2)])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_ylabel("Share of incidents")
    ax.set_title("When incidents start: hour of day", y=1.06)
    subtitle(ax, "Top 3 hours highlighted (labels = % of incidents) · exact 00:00:00 / 12:00:00 'time unknown' defaults "
                 "excluded, so 00:00 and 12:00 read slightly low")
    ax.grid(axis="x", visible=False)
    save(fig, "02_hour_of_day.png")
    out["peak_hours"] = [{"hour": fmt_hour(int(h)), "share_pct": round(float(prof.loc[h, "share"]) * 100, 2)}
                         for h in top3]
    quiet = prof["incidents"].idxmin()
    out["quietest_hour"] = fmt_hour(int(quiet))
    out["peak_to_trough_ratio"] = round(float(prof["incidents"].max() / prof["incidents"].min()), 1)
    tb = A.timed(df)["time_band"].value_counts(normalize=True).mul(100).round(1)
    out["share_by_time_band_pct"] = {str(k): float(v) for k, v in tb.items()}


def fig_day_hour_heatmap(df, out):
    m = A.day_hour_matrix(df)
    fig, ax = plt.subplots(figsize=(11, 3.8))
    im = ax.imshow(m.values, aspect="auto", cmap=SEQ)
    ax.set_yticks(range(7), m.index)
    ax.set_xticks(range(0, 24, 2), [fmt_hour(h) for h in range(0, 24, 2)])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    r, c = np.unravel_index(np.argmax(m.values), m.shape)
    ax.add_patch(plt.Rectangle((c - .5, r - .5), 1, 1, fill=False, ec=ORANGE, lw=2))
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=INK2, labelsize=8)
    cb.set_label("Incidents", color=INK2)
    ax.set_title("Weekly rhythm: incidents by day and hour", y=1.08)
    subtitle(ax, f"Darker = more incidents · busiest slot ({m.index[r]} {fmt_hour(c)}) outlined in orange")
    save(fig, "03_day_hour_heatmap.png")
    out["busiest_day_hour"] = f"{m.index[r]} {fmt_hour(c)}"
    dow = A.timed(df)["day_name"].value_counts()
    out["busiest_day"] = str(dow.idxmax())
    out["quietest_day"] = str(dow.idxmin())
    wk = A.timed(df)
    out["late_night_weekend_share_pct"] = round(100 * float(
        (wk["is_weekend"] & (wk["hour"] < 4)).sum() / max(1, (wk["hour"] < 4).sum())), 1)


def fig_hotspot_map(df, out):
    d = df[df["has_valid_coords"]]
    cells = A.hotspot_cells(df, top=10)
    fig, ax = plt.subplots(figsize=(8.5, 8))
    hb = ax.hexbin(d["longitude"], d["latitude"], gridsize=70, cmap=SEQ, bins="log", mincnt=1, linewidths=0.2,
                   edgecolors=SURFACE)
    placed = []
    offsets = [(0.014, 0), (-0.014, 0), (0, 0.013), (0, -0.013), (0.014, 0.011), (-0.014, -0.011)]
    for i, (gid, row) in enumerate(cells.iterrows(), start=1):
        ax.scatter(row["lon"], row["lat"], s=110, facecolor="none", edgecolor=ORANGE, lw=2, zorder=3)
        for dx, dy in offsets:                      # first position not clashing with an earlier label/ring
            x, y = row["lon"] + dx, row["lat"] + dy
            if all(abs(x - px) > 0.016 or abs(y - py) > 0.010 for px, py in placed):
                break
        placed += [(x, y), (row["lon"], row["lat"])]
        ax.text(x, y, f"{i}", color=INK, fontsize=9, fontweight="bold", va="center", ha="center",
                zorder=4, bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none", alpha=0.9))
    ax.set_aspect(1 / np.cos(np.deg2rad(39.1)))
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(False)
    cb = fig.colorbar(hb, ax=ax, fraction=0.035, pad=0.02)
    cb.outline.set_visible(False)
    cb.set_label("Incidents per hexagon (log scale)", color=INK2)
    ax.set_title("Where incidents concentrate", y=1.04)
    subtitle(ax, "Density of geocoded incidents · numbered rings = top 10 ~1 km grid cells (see next chart)")
    save(fig, "04_hotspot_density_map.png")


def fig_top_hotspots(df, out):
    cells = A.hotspot_cells(df, top=10)
    labels = [f"{i}. {str(r.city).title()} — {str(r.top_block).title()}"
              for i, r in enumerate(cells.itertuples(), start=1)]
    fig, ax = plt.subplots(figsize=(10, 5))
    y = np.arange(len(cells))[::-1]
    ax.barh(y, cells["incidents"], color=BLUE, height=0.65)
    for yi, (n, s) in zip(y, zip(cells["incidents"], cells["share_of_county"])):
        ax.text(n, yi, f"  {n:,}  ({s:.1%})", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, labels)
    ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
    ax.set_xlim(0, cells["incidents"].max() * 1.22)
    ax.grid(axis="y", visible=False)
    ax.set_title("Top 10 hotspot grid cells", y=1.06)
    subtitle(ax, "≈1 km cells, labelled with the most frequent city and block address · % of all geocoded incidents")
    save(fig, "05_top_hotspots.png")
    conc = A.concentration(df, 0.05)
    out["hotspots_top10"] = [
        {"rank": i, "city": str(r.city).title(), "top_block": str(r.top_block).title(),
         "incidents": int(r.incidents), "share_pct": round(100 * float(r.share_of_county), 2),
         "top_category": str(r.top_category), "lat": float(r.lat), "lon": float(r.lon)}
        for i, r in enumerate(cells.itertuples(), start=1)]
    out["top10_cells_share_pct"] = round(100 * float(cells["share_of_county"].sum()), 1)
    out["top5pct_cells_share_pct"] = round(100 * conc, 1)
    out["occupied_grid_cells"] = int(df.loc[df["has_valid_coords"], "grid_id"].nunique())


def fig_hour_by_crime_type(df, out):
    d = df[df["crime_against"].astype("string").str.contains("Person|Property|Society", case=False, na=False)]
    prof = A.hourly_profile(d, by="crime_against")
    fig, ax = plt.subplots(figsize=(10, 4.2))
    order = [("Crime Against Property", BLUE), ("Crime Against Person", ORANGE), ("Crime Against Society", AQUA)]
    for name, col in order:
        s = prof[prof["crime_against"].astype(str).str.lower() == name.lower()]
        if s.empty:
            continue
        ax.plot(s["hour"], s["share"] * 100, color=col, lw=2, label=name.replace("Crime Against ", "Against "))
        last = s.iloc[-1]
        ax.text(23.3, last["share"] * 100, name.replace("Crime Against ", ""), color=INK, fontsize=9, va="center")
        pk = s.loc[s["share"].idxmax()]
        out.setdefault("peak_hour_by_type", {})[name] = fmt_hour(int(pk["hour"]))
    ax.set_xticks(range(0, 24, 2), [fmt_hour(h) for h in range(0, 24, 2)])
    ax.set_xlim(0, 25.5)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_ylabel("Share of that type's incidents")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncols=3)
    ax.grid(axis="x", visible=False)
    ax.set_title("Different crimes peak at different times", y=1.06)
    subtitle(ax, "Hourly profile within each NIBRS 'crime against' group (each line sums to 100%)")
    save(fig, "06_hour_by_crime_type.png")


def fig_districts(df, out):
    ds = A.district_summary(df).head(8)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    y = np.arange(len(ds))[::-1]
    ax.barh(y, ds["incidents"], color=BLUE, height=0.65)
    for yi, n, s in zip(y, ds["incidents"], ds["share_pct"]):
        ax.text(n, yi, f"  {n:,.0f}  ({s:.0f}%)", va="center", fontsize=9)
    ax.set_yticks(y, [str(i).title() for i in ds.index])
    ax.set_xlim(0, ds["incidents"].max() * 1.2)
    ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
    ax.grid(axis="y", visible=False)
    ax.set_title("Incidents by police district", y=1.06)
    subtitle(ax, "All years in the extract")
    save(fig, "07_police_districts.png")
    out["districts"] = {str(k).title(): float(v) for k, v in ds["share_pct"].items()}


def fig_categories(df, out):
    cats = A.top_categories(df, 10)
    total = len(df)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(cats))[::-1]
    ax.barh(y, cats.values, color=BLUE, height=0.65)
    for yi, n in zip(y, cats.values):
        ax.text(n, yi, f"  {n:,}  ({n / total:.0%})", va="center", fontsize=9)
    ax.set_yticks(y, [str(c) for c in cats.index])
    ax.set_xlim(0, cats.max() * 1.22)
    ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
    ax.grid(axis="y", visible=False)
    ax.set_title("Most common offence categories", y=1.06)
    subtitle(ax, "NIBRS 'Crime Name 2' · share of all incidents")
    save(fig, "08_top_categories.png")
    out["top_categories"] = {str(k): round(100 * v / total, 1) for k, v in cats.head(5).items()}


def interactive_map(df):
    try:
        import folium
        from folium.plugins import HeatMap
    except ImportError:
        print("  folium not installed – skipping interactive map")
        return
    d = df[df["has_valid_coords"]]
    sample = d.sample(min(len(d), 60000), random_state=1)
    m = folium.Map(location=[39.1, -77.15], zoom_start=10, tiles="cartodbpositron")
    HeatMap(sample[["latitude", "longitude"]].to_numpy().tolist(), radius=7, blur=9, min_opacity=0.25).add_to(m)
    for i, r in enumerate(A.hotspot_cells(df, top=10).itertuples(), start=1):
        folium.CircleMarker([r.lat, r.lon], radius=9, color=ORANGE, weight=2, fill=False,
                            tooltip=f"#{i} {str(r.city).title()} – {str(r.top_block).title()}: {r.incidents:,} incidents"
                            ).add_to(m)
    m.save(ROOT / "reports" / "hotspot_map.html")
    print("  saved hotspot_map.html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clean_parquet", nargs="?", default=str(ROOT / "data" / "processed" / "crime_clean.parquet"))
    args = ap.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)
    df_all = pd.read_parquet(args.clean_parquet)
    df = df_all[df_all["is_crime"]].copy()          # analyse genuine offences only
    out = {
        "rows_clean": len(df_all),
        "rows_analysed": len(df),
        "non_crime_records_excluded": int((~df_all["is_crime"]).sum()),
        "date_range": [f"{df['start_datetime'].min():%Y-%m-%d}", f"{df['start_datetime'].max():%Y-%m-%d}"],
        "pct_valid_coords": round(100 * df["has_valid_coords"].mean(), 1),
        "pct_time_placeholder": round(100 * df["time_placeholder"].mean(), 1),
        "median_report_lag_hours": round(float(df["report_lag_hours"].median()), 2)
        if "report_lag_hours" in df else None,
    }
    for f in (fig_monthly_trend, fig_hour_of_day, fig_day_hour_heatmap, fig_hotspot_map, fig_top_hotspots,
              fig_hour_by_crime_type, fig_districts, fig_categories):
        f(df, out)
    interactive_map(df)
    (ROOT / "reports" / "findings.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
