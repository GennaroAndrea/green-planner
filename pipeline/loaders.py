"""Loaders + cleaning for the raw datasets in data/raw/ (Phase 1.1).

Every spatial loader returns data in the compute CRS (EPSG:32633).
"""

import json
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline.config import RAW_DIR, project_path

COMPUTE_CRS = "EPSG:32633"
WEB_CRS = "EPSG:4326"


def _read_zip(path: Path, inner: str | None = None, **kwargs: Any) -> gpd.GeoDataFrame:
    uri = f"zip://{path}" + (f"!{inner}" if inner else "")
    gdf = gpd.read_file(uri, **kwargs)
    return gdf.to_crs(COMPUTE_CRS)


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def load_boundary() -> gpd.GeoDataFrame:
    """Municipal boundary (SIT, D8), one row."""
    gdf = _read_zip(RAW_DIR / "sit" / "confine_comunale.zip")
    return gpd.GeoDataFrame(geometry=[gdf.union_all().buffer(0)], crs=COMPUTE_CRS)


def load_zones(config: dict[str, Any]) -> gpd.GeoDataFrame:
    """SIT quartieri dissolved to one polygon per quartiere, with ids/names from the config."""
    raw = _read_zip(RAW_DIR / "sit" / "quartieri.zip")
    raw["geometry"] = raw.geometry.buffer(0)
    dissolved = raw.dissolve(by="nome", as_index=False)[["nome", "geometry"]]
    items = pd.DataFrame(config["zones"]["items"])
    zones = dissolved.merge(items, left_on="nome", right_on="sit_name", how="left")
    missing = zones[zones["id"].isna()]["nome"].tolist()
    if missing:
        raise ValueError(f"Quartieri without a config entry: {missing}")
    zones["covered"] = zones["rione"].notna()
    zones = zones.rename(columns={"id": "zone_id"})[
        ["zone_id", "name", "rione", "covered", "geometry"]
    ]
    return zones.sort_values("zone_id").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Green areas (D1) and land use
# ---------------------------------------------------------------------------


def load_green_areas() -> gpd.GeoDataFrame:
    gdf = _read_zip(RAW_DIR / "green_areas" / "aree-verdi-2.zip")
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf[~gdf.geometry.is_empty]
    return gdf[["id", "nome_area", "id_tipo_ar", "geometry"]].reset_index(drop=True)


def load_artificial_surfaces(bounds: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Uso del Suolo 2011, class 1 (artificial surfaces), limited to a bounding box."""
    gdf = _read_zip(
        RAW_DIR / "land_use_2011" / "udssuperficiartificiali.zip",
        "UdS-SuperficiArtificiali/SuperficiArtificiali.shp",
        bbox=bounds,
    )
    gdf = gdf[gdf["LIVELLO_1"] == 1]
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf[["CODICE", "geometry"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Population (D6) + civic numbers (D8)
# ---------------------------------------------------------------------------


def normalise_street(name: str) -> str:
    """Canonical street name for address matching: upper case, no accents/punctuation."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


def split_civic(civic: str) -> tuple[str, str]:
    """'12/A' -> ('12', 'A'), '12' -> ('12', ''). Non-numeric civics keep their text."""
    text = str(civic).strip().upper().replace(" ", "")
    m = re.match(r"^0*(\d+)(?:/?(.*))?$", text)
    if not m:
        return text, ""
    return m.group(1), (m.group(2) or "").strip("/")


def load_population() -> pd.DataFrame:
    """Residents per address: total (under67 + over67) and vulnerable (under14 + over67).

    The source CSVs are cumulative age bands (under14 ⊂ under18 ⊂ under67), see §3 of the plan.
    """
    frames = {}
    for band in ("under14", "under67", "over67"):
        df = pd.read_csv(RAW_DIR / "population" / f"{band}.csv", dtype=str)
        df["n"] = pd.to_numeric(df["NUM_RESIDENTI"], errors="coerce").fillna(0).astype(int)
        frames[band] = df.groupby(["VIA", "CIVICO", "RIONE"], as_index=False)["n"].sum()
    keys = ["VIA", "CIVICO", "RIONE"]
    pop = frames["under67"].rename(columns={"n": "under67"})
    for band in ("over67", "under14"):
        pop = pop.merge(frames[band].rename(columns={"n": band}), on=keys, how="outer")
    pop = pop.fillna({"under67": 0, "over67": 0, "under14": 0})
    pop["residents"] = (pop["under67"] + pop["over67"]).astype(int)
    pop["vulnerable"] = (pop["under14"] + pop["over67"]).astype(int)
    pop["street_key"] = pop["VIA"].map(normalise_street)
    civ = pop["CIVICO"].map(split_civic)
    pop["number"] = civ.str[0]
    pop["suffix"] = civ.str[1]
    return pop.rename(columns={"RIONE": "rione"})[
        ["street_key", "number", "suffix", "rione", "residents", "vulnerable"]
    ]


def load_civics() -> gpd.GeoDataFrame:
    """SIT civic-number points with normalised match keys."""
    gdf = _read_zip(RAW_DIR / "sit" / "civici.zip")
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    gdf["street_key"] = gdf["denom_via"].map(normalise_street)
    gdf["number"] = gdf["numero"].astype(str).str.strip().str.lstrip("0")
    gdf["suffix"] = gdf["esponente"].fillna("").astype(str).str.strip().str.upper()
    return gdf[["street_key", "number", "suffix", "geometry"]].reset_index(drop=True)


def place_population(
    pop: pd.DataFrame, civics: gpd.GeoDataFrame, zones: gpd.GeoDataFrame
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Place residents on civic-number points (Q4b).

    1. exact match on street + number + suffix;
    2. then street + number (suffix ignored);
    3. unmatched residents are spread over the civic points of their quartiere, in equal shares.

    Returns weighted points (residents, vulnerable) and match statistics.
    """
    civics = civics.sjoin(zones[["rione", "geometry"]], how="left", predicate="within")
    civics = civics.drop(columns="index_right")

    exact = civics.drop_duplicates(["street_key", "number", "suffix"])
    base = civics.drop_duplicates(["street_key", "number"])

    m1 = pop.merge(exact, on=["street_key", "number", "suffix"], how="left", suffixes=("", "_c"))
    matched1 = m1[m1.geometry.notna()]
    rest = pop.loc[m1.geometry.isna().to_numpy()]
    m2 = rest.merge(
        base.drop(columns="suffix"), on=["street_key", "number"], how="left", suffixes=("", "_c")
    )
    matched2 = m2[m2.geometry.notna()]
    unmatched = m2[m2.geometry.isna()]

    cols = ["residents", "vulnerable", "geometry"]
    points = [matched1[cols], matched2[cols]]

    # Fallback: spread each rione's unmatched residents over the civic points in its quartiere
    unmatched_by_rione = unmatched.groupby("rione")[["residents", "vulnerable"]].sum()
    lost = 0
    for rione, row in unmatched_by_rione.iterrows():
        targets = civics[civics["rione"] == rione]
        if targets.empty:
            lost += int(row["residents"])
            continue
        share = 1.0 / len(targets)
        points.append(
            pd.DataFrame(
                {
                    "residents": row["residents"] * share,
                    "vulnerable": row["vulnerable"] * share,
                    "geometry": targets.geometry.to_numpy(),
                }
            )
        )
    placed = gpd.GeoDataFrame(pd.concat(points, ignore_index=True), crs=COMPUTE_CRS)
    total = int(pop["residents"].sum())
    stats = {
        "residents_total": total,
        "residents_matched_exact": int(matched1["residents"].sum()),
        "residents_matched_number": int(matched2["residents"].sum()),
        "residents_spread_by_zone": int(unmatched["residents"].sum()) - lost,
        "residents_not_placed": lost,
    }
    stats["match_rate"] = round(
        (stats["residents_matched_exact"] + stats["residents_matched_number"]) / total, 4
    )
    return placed, stats


# ---------------------------------------------------------------------------
# Traffic (D2 flows + D3 controller positions)
# ---------------------------------------------------------------------------

CONTROLLER_KEY = ["device_db", "device_type", "device_id"]


def _month_of(path: Path) -> str:
    m = re.search(r"(\d{4})(\d{2})", path.stem)
    if not m:
        raise ValueError(f"No YYYYMM in file name: {path.name}")
    return f"{m.group(1)}-{m.group(2)}"


def load_traffic_controllers() -> gpd.GeoDataFrame:
    """Controller positions, merged over all monthly files (the latest valid position wins)."""
    rows = []
    for path in sorted((RAW_DIR / "traffic_controllers").glob("*.json")):
        month = _month_of(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        for c in data["traffic_controllers_info"]:
            p = c.get("properties", {})
            lat, lon = p.get("latitude"), p.get("longitude")
            if not lat or not lon:  # (0, 0) or missing: invalid position
                continue
            rows.append(
                {
                    "device_db": int(c["device_db"]),
                    "device_type": int(c["device_type"]),
                    "device_id": int(c["device_id"]),
                    "code": p.get("code"),
                    "name": p.get("name"),
                    "n_detectors": len(c.get("detectors", [])),
                    "lat": float(lat),
                    "lon": float(lon),
                    "month": month,
                }
            )
    df = pd.DataFrame(rows).sort_values("month").drop_duplicates(CONTROLLER_KEY, keep="last")
    gdf = gpd.GeoDataFrame(
        df.drop(columns=["lat", "lon", "month"]),
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs=WEB_CRS,
    )
    return gdf.to_crs(COMPUTE_CRS).reset_index(drop=True)


def load_traffic_flows(
    exclude_months: list[str], zero_is_missing: bool, max_daily: float | None = None
) -> pd.DataFrame:
    """Daily vehicle counts per detector, long format: key + detector_id, date, vehicles.

    Invalid readings (negative, zero if `zero_is_missing`, above `max_daily`) become NaN.
    """
    frames = []
    for path in sorted((RAW_DIR / "traffic_flows").glob("*.csv")):
        month = _month_of(path)
        if month in exclude_months:
            continue
        df = pd.read_csv(path)
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
        ids = CONTROLLER_KEY + ["detector_id"]
        long = df.melt(id_vars=ids, var_name="date", value_name="vehicles")
        long["date"] = pd.to_datetime(long["date"], format="%d/%m/%Y")
        long["month"] = month
        frames.append(long)
    flows = pd.concat(frames, ignore_index=True)
    flows["vehicles"] = pd.to_numeric(flows["vehicles"], errors="coerce")
    flows.loc[flows["vehicles"] < 0, "vehicles"] = np.nan
    if zero_is_missing:
        flows.loc[flows["vehicles"] == 0, "vehicles"] = np.nan
    if max_daily is not None:
        flows.loc[flows["vehicles"] > max_daily, "vehicles"] = np.nan
    return flows


def controller_daily_means(
    flows: pd.DataFrame, controllers: gpd.GeoDataFrame, outlier_iqr_factor: float
) -> gpd.GeoDataFrame:
    """Mean daily vehicles per controller (Q8a): sum over detectors of each detector's mean.

    Averaging per detector first means a missing day on one detector doesn't lower the total.
    """
    det = (
        flows.dropna(subset=["vehicles"])
        .groupby(CONTROLLER_KEY + ["detector_id"])["vehicles"]
        .agg(mean="mean", days="count")
        .reset_index()
    )
    ctl = (
        det.groupby(CONTROLLER_KEY)
        .agg(vehicles_day=("mean", "sum"), detectors_with_data=("mean", "size"))
        .reset_index()
    )
    gdf = controllers.merge(ctl, on=CONTROLLER_KEY, how="inner")
    q1, q3 = gdf["vehicles_day"].quantile([0.25, 0.75])
    gdf["suspicious_total"] = gdf["vehicles_day"] > q3 + outlier_iqr_factor * (q3 - q1)
    return gdf


# ---------------------------------------------------------------------------
# Air quality (D5 stations + manual 2025 annual means)
# ---------------------------------------------------------------------------

POLLUTANT_COLUMNS = {"NO2": "no2_ugm3", "PM10": "pm10_ugm3", "PM2.5": "pm25_ugm3"}


def load_air_stations(config: dict[str, Any]) -> gpd.GeoDataFrame:
    """Bari stations with annual means and the pollution ratio (mean of conc / EU limit)."""
    air = config["air"]
    raw = json.loads((RAW_DIR / "air_stations" / "stations.geojson").read_text(encoding="utf-8"))
    rows = [
        {
            "id_station": int(f["properties"]["id_station"]),
            "lon": f["geometry"]["coordinates"][0],
            "lat": f["geometry"]["coordinates"][1],
        }
        for f in raw["features"]
    ]
    pos = pd.DataFrame(rows)
    means = pd.read_csv(project_path(air["annual_means_file"]))
    df = means.merge(pos, on="id_station", how="left")
    if df["lon"].isna().any():
        raise ValueError("ARPA stations in the annual means file without a position")
    ratios = [df[POLLUTANT_COLUMNS[p]] / air["limit_values_ugm3"][p] for p in air["pollutants"]]
    df["pollution_ratio"] = pd.concat(ratios, axis=1).mean(axis=1, skipna=True)
    df["pollutants_measured"] = pd.concat(ratios, axis=1).notna().sum(axis=1)
    gdf = gpd.GeoDataFrame(
        df.drop(columns=["lon", "lat"]),
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs=WEB_CRS,
    )
    return gdf.to_crs(COMPUTE_CRS)


# ---------------------------------------------------------------------------
# Industry (D10, E-PRTR)
# ---------------------------------------------------------------------------

EPRTR_POLLUTANTS = {"NOX": "Nitrogen oxides (NOX)", "PM10": "Particulate matter (PM10)"}


def load_industry(
    config: dict[str, Any], boundary: gpd.GeoDataFrame
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """E-PRTR facilities within the radius, with their latest NOx/PM10 air releases (kg/year).

    `recent` marks facilities that reported in the last N reporting years (Q18).
    """
    ind = config["industry"]
    names = [EPRTR_POLLUTANTS[p] for p in ind["pollutants"]]
    with zipfile.ZipFile(RAW_DIR / "eprtr" / "eprtr_csv_v16.zip") as z:
        with z.open("F1_4_Air_Releases_Facilities.csv") as f:
            df = pd.read_csv(
                f,
                encoding="utf-8-sig",
                usecols=[
                    "countryName", "reportingYear", "FacilityInspireId", "facilityName",
                    "city", "Longitude", "Latitude", "Pollutant", "Releases",
                ],
            )  # fmt: skip
    last_year = int(df["reportingYear"].max())
    df = df[(df["countryName"] == "Italy") & df["Pollutant"].isin(names)]
    df = df.dropna(subset=["Longitude", "Latitude"])
    gdf = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]), crs=WEB_CRS
    ).to_crs(COMPUTE_CRS)
    area = boundary.geometry.iloc[0].buffer(ind["radius_km"] * 1000)
    gdf = gdf[gdf.within(area)]

    latest = gdf.groupby("FacilityInspireId")["reportingYear"].transform("max")
    gdf = gdf[gdf["reportingYear"] == latest]
    fac = (
        gdf.pivot_table(
            index=["FacilityInspireId", "facilityName", "city", "reportingYear"],
            columns="Pollutant",
            values="Releases",
            aggfunc="sum",
        )
        .reset_index()
        .rename(columns={v: f"{k.lower()}_kg" for k, v in EPRTR_POLLUTANTS.items()})
    )
    geoms = gdf.drop_duplicates("FacilityInspireId").set_index("FacilityInspireId").geometry
    fac = gpd.GeoDataFrame(
        fac, geometry=fac["FacilityInspireId"].map(geoms).to_numpy(), crs=COMPUTE_CRS
    )
    fac.columns.name = None
    for col in ("nox_kg", "pm10_kg"):
        if col not in fac:
            fac[col] = np.nan
    fac["recent"] = fac["reportingYear"] > last_year - ind["recent_years"]
    fac = fac.rename(
        columns={
            "FacilityInspireId": "facility_id",
            "facilityName": "name",
            "reportingYear": "last_reporting_year",
        }
    )
    n_recent = int(fac["recent"].sum())
    info = {
        "facilities_in_radius": len(fac),
        "facilities_recent": n_recent,
        "last_reporting_year": last_year,
        "active": n_recent >= ind["min_facilities"],
    }
    return fac.reset_index(drop=True), info
