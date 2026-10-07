"""Unit tests for the cleaning steps, using a tiny hand-made messy extract."""
import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crime_pipeline import CORE_STEPS, CleaningPipeline  # noqa: E402
from crime_pipeline import analysis, cleaning  # noqa: E402

RAW = """Incident ID,Offence Code,CR Number,Dispatch Date / Time,Start_Date_Time,End_Date_Time,NIBRS Code,Victims,Crime Name1,Crime Name2,Crime Name3,Police District Name,Block Address,City,State,Zip Code,Agency,Place,Sector,Beat,PRA,Latitude,Longitude
201,2305,1,07/01/2023 10:15:00 PM,07/01/2023 09:50:00 PM,07/01/2023 10:00:00 PM,23F,1,Crime Against Property,Theft From Motor Vehicle,LARCENY - FROM AUTO,SILVER SPRING,8500 BLK GEORGIA AVE,silver sprng ,MD,20910,MCPD,Street - Other,G,3G1,1,38.9951,-77.0262
201,2305,1,07/01/2023 10:15:00 PM,07/01/2023 09:50:00 PM,07/01/2023 10:00:00 PM,23F,1,Crime Against Property,Theft From Motor Vehicle,LARCENY - FROM AUTO,SILVER SPRING,8500 BLK GEORGIA AVE,silver sprng ,MD,20910,MCPD,Street - Other,G,3G1,1,38.9951,-77.0262
202,1399,2,07/02/2023 01:05:00 AM,07/02/2023 12:55:00 AM,,13B,1,Crime Against Person,Simple Assault,ASSAULT - SIMPLE,ROCKVILLE,100 BLK N WASHINGTON ST,Rockville,MD,20850-1234,MCPD,Bar/Club,A,1A1,2,39.0840,-77.1528
203,2399,3,07/03/2023 08:00:00 AM,07/03/2023 07:00:00 AM,07/02/2023 11:00:00 PM,23H,1,Crime Against Property,All Other Larceny,LARCENY,GERMANTOWN,  ,GERMANTOWN,MD,ABCDE,MCPD,Residence,M,5M1,3,0,0
204,9999,4,07/04/2023 12:00:00 PM,,,90Z,0,Crime Against Society,All Other Offenses,ALL OTHER,WHEATON,2400 BLK UNIVERSITY BLVD,WHEATON,MD,20902,MCPD,Street,K,4K1,4,39.0410,-77.0520
205,2305,5,07/05/2023 06:30:00 PM,07/05/2023 12:00:00 AM,,23F,1,Crime Against Property,Theft From Motor Vehicle,LARCENY - FROM AUTO,BETHESDA,7700 BLK WISCONSIN AVE,BETHSEDA,MD,20814,MCPD,Parking Lot,D,2D1,5,38.9850,-77.0940
"""


@pytest.fixture()
def raw() -> pd.DataFrame:
    return pd.read_csv(io.StringIO(RAW), dtype="string")


@pytest.fixture()
def clean(raw) -> pd.DataFrame:
    return CleaningPipeline(CORE_STEPS).run(raw)


def test_columns_are_canonical(clean):
    for col in ["incident_id", "start_datetime", "crime_category", "district", "latitude", "hour"]:
        assert col in clean.columns


def test_exact_duplicates_removed_and_missing_start_dropped(clean):
    # 6 raw rows: 1 exact duplicate + 1 row without a start date
    assert len(clean) == 4
    assert clean["incident_id"].is_unique


def test_datetime_parsing_uses_12h_clock(clean):
    row = clean.loc[clean["incident_id"] == 202].iloc[0]
    assert row["start_datetime"] == pd.Timestamp("2023-07-02 00:55:00")
    assert row["hour"] == 0


def test_swapped_start_end_fixed(clean):
    row = clean.loc[clean["incident_id"] == 203].iloc[0]
    assert row["start_datetime"] <= row["end_datetime"]


def test_city_variants_fixed(clean):
    assert set(clean["city"].astype(str)) == {"SILVER SPRING", "ROCKVILLE", "GERMANTOWN", "BETHESDA"}


def test_fuzzy_city_matching():
    m = cleaning.build_city_map(["SILVER SRING", "GAITHESBURG", "GERMATOWN", "ROCKVILLE", "ZZZ"])
    assert m["SILVER SRING"] == "SILVER SPRING"
    assert m["GAITHESBURG"] == "GAITHERSBURG"
    assert m["GERMATOWN"] == "GERMANTOWN"
    assert m["ROCKVILLE"] == "ROCKVILLE"
    assert pd.isna(m["ZZZ"])


def test_zip_codes_normalised(clean):
    zips = clean.set_index("incident_id")["zip_code"]
    assert zips.loc[202] == "20850"
    assert pd.isna(zips.loc[203])


def test_invalid_coordinates_nulled(clean):
    row = clean.loc[clean["incident_id"] == 203].iloc[0]
    assert pd.isna(row["latitude"]) and not row["has_valid_coords"]
    assert clean["has_valid_coords"].sum() == 3


def test_time_placeholder_flagged(clean):
    assert bool(clean.loc[clean["incident_id"] == 205, "time_placeholder"].iloc[0])


def test_pipeline_is_idempotent(clean):
    again = CleaningPipeline(CORE_STEPS[1:]).run(clean.copy())  # skip header mapping
    assert len(again) == len(clean)


def test_report_records_every_step(raw):
    pipe = CleaningPipeline(CORE_STEPS)
    pipe.run(raw)
    rep = pipe.report_frame()
    assert list(rep["step"]) == [s.__name__ for s in CORE_STEPS]
    assert rep["rows_removed"].sum() == 2


def test_hotspots_and_peaks(clean):
    cells = analysis.hotspot_cells(clean, top=5)
    assert cells["incidents"].sum() == 3
    peaks = analysis.peak_hours(clean, n=1)
    assert len(peaks) == 1
