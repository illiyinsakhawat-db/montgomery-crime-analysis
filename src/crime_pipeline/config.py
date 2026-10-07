"""
Configuration for the Montgomery County (MD) crime cleaning pipeline.

Everything that is specific to the source extract lives here, so the same
pipeline can be reused for new yearly/monthly extracts (or a different
county's open-data feed) by editing config rather than code.
"""

# Source: Montgomery County Open Data portal, dataset "Crime" (icn6-v9z3)
SOURCE_URL = "https://data.montgomerycountymd.gov/api/views/icn6-v9z3/rows.csv?accessType=DOWNLOAD"

# Raw column header -> canonical snake_case name.
# Headers are first lower-cased and stripped of punctuation, then looked up here,
# so small header changes between extracts ("Start_Date_Time" vs "Start Date Time")
# don't break the pipeline.
COLUMN_ALIASES = {
    "incident_id": "incident_id",
    "offence_code": "offence_code",
    "offense_code": "offence_code",
    "cr_number": "case_number",
    "case_number": "case_number",
    "dispatch_date_time": "dispatch_datetime",
    "dispatch_date": "dispatch_datetime",
    "date": "dispatch_datetime",
    "start_date_time": "start_datetime",
    "start_date": "start_datetime",
    "end_date_time": "end_datetime",
    "end_date": "end_datetime",
    "nibrs_code": "nibrs_code",
    "victims": "victims",
    "crime_name1": "crime_against",
    "crimename1": "crime_against",
    "crime_name2": "crime_category",
    "crimename2": "crime_category",
    "crime_name3": "crime_detail",
    "crimename3": "crime_detail",
    "police_district_name": "district",
    "district": "district",
    "block_address": "block_address",
    "location": "block_address_or_point",
    "city": "city",
    "state": "state",
    "zip_code": "zip_code",
    "agency": "agency",
    "place": "place",
    "sector": "sector",
    "beat": "beat",
    "pra": "pra",
    "latitude": "latitude",
    "longitude": "longitude",
    "police_district_number": "district_number",
}

# Only the columns the analysis needs are loaded (usecols) -> faster + less memory
KEEP_COLUMNS = [
    "incident_id", "offence_code", "dispatch_datetime", "start_datetime", "end_datetime",
    "nibrs_code", "victims", "crime_against", "crime_category", "crime_detail",
    "district", "block_address", "city", "zip_code", "agency", "place", "sector", "beat",
    "latitude", "longitude",
]

# Explicit datetime format avoids slow per-row format inference
DATETIME_FORMATS = ["%m/%d/%Y %I:%M:%S %p", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]

# Montgomery County bounding box (generous) – anything outside is a geocoding error
LAT_RANGE = (38.90, 39.36)
LON_RANGE = (-77.53, -76.88)

# Low-cardinality text columns stored as pandas 'category' (big memory saving)
CATEGORICAL_COLUMNS = [
    "crime_against", "crime_category", "crime_detail", "district", "city", "agency",
    "place", "sector", "beat", "nibrs_code", "time_band", "day_name",
]

# Canonical place names used by the fuzzy city matcher (Montgomery County + border towns)
CANONICAL_CITIES = [
    "ASHTON", "ASPEN HILL", "BARNESVILLE", "BEALLSVILLE", "BELTSVILLE", "BETHESDA", "BOYDS", "BRINKLOW",
    "BROOKEVILLE", "BURTONSVILLE", "CABIN JOHN", "CHEVY CHASE", "CLARKSBURG", "COLESVILLE", "DAMASCUS",
    "DARNESTOWN", "DERWOOD", "DICKERSON", "GAITHERSBURG", "GARRETT PARK", "GERMANTOWN", "GLEN ECHO",
    "HIGHLAND", "HYATTSVILLE", "KENSINGTON", "LAUREL", "LAYTONSVILLE", "MONTGOMERY VILLAGE", "MOUNT AIRY",
    "NORTH BETHESDA", "NORTH POTOMAC", "OLNEY", "POOLESVILLE", "POTOMAC", "ROCKVILLE", "SANDY SPRING",
    "SILVER SPRING", "SPENCERVILLE", "TAKOMA PARK", "WASHINGTON GROVE", "WHEATON", "WOODBINE", "ADELPHI",
    "LANHAM", "FRIENDSHIP HEIGHTS", "WASHINGTON",
]
# Minimum similarity (0-1) for a fuzzy match to be accepted
CITY_MATCH_CUTOFF = 0.84

# Abbreviations / variants that fuzzy matching can't infer – applied first
CITY_FIXES = {
    "TP": "TAKOMA PARK",
    "GA": "GAITHERSBURG",
    "RO": "ROCKVILLE",
    "PO": "POTOMAC",
    "SS": "SILVER SPRING",
    "SILVER": "SILVER SPRING",
    "MT AIRY": "MOUNT AIRY",
    "MT. AIRY": "MOUNT AIRY",
    "N POTOMAC": "NORTH POTOMAC",
    "WASHINGTON DC": "WASHINGTON",
    "HYATTSVILLE PG": "HYATTSVILLE",
    "BROOKVILLE": "BROOKEVILLE",
    "SILVER SPRNG": "SILVER SPRING",
    "SILVERSPRING": "SILVER SPRING",
    "SILVER SPRINGS": "SILVER SPRING",
    "GAITHERBURG": "GAITHERSBURG",
    "GAITHERSBURGH": "GAITHERSBURG",
    "GAITHERSBUG": "GAITHERSBURG",
    "GERMANTOWN MD": "GERMANTOWN",
    "N BETHESDA": "NORTH BETHESDA",
    "NORTH BETHSEDA": "NORTH BETHESDA",
    "BETHSEDA": "BETHESDA",
    "ROCKVIILE": "ROCKVILLE",
    "ROCKVILE": "ROCKVILLE",
    "TAKOMA PK": "TAKOMA PARK",
    "MONTGOMERY VILLAGE": "MONTGOMERY VILLAGE",
    "WHEATON GLENMONT": "WHEATON",
}

# Hour-of-day bands used in the EDA
TIME_BANDS = [
    (0, 6, "Night (00-05)"),
    (6, 12, "Morning (06-11)"),
    (12, 18, "Afternoon (12-17)"),
    (18, 24, "Evening (18-23)"),
]

# Grid size (degrees) for hotspot density: 0.01 deg ≈ 1.1 km N-S, ≈ 0.86 km E-W at 39°N
HOTSPOT_GRID_DEG = 0.01
