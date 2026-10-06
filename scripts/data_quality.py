"""Validate raw geographic records before aggregation; retain an auditable review."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

PREFIX = "geolocation_zip_code_prefix"
LAT = "geolocation_lat"
LNG = "geolocation_lng"

def _prefix_key(value):
    if isinstance(value, (bool, np.bool_)) or pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value.isascii() or not value.isdigit() or len(value) > 5:
            return None
        number = int(value)
    elif isinstance(value, (int, np.integer)):
        number = int(value)
    elif isinstance(value, (float, np.floating)):
        if not np.isfinite(value) or not float(value).is_integer():
            return None
        number = int(value)
    else:
        return None
    return f"{number:05d}" if 0 <= number <= 99999 else None

def _load_region(geojson, codes):
    if isinstance(geojson, (str, Path)):
        geojson = json.loads(Path(geojson).read_text(encoding="utf-8-sig"))
    if geojson.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON must be a FeatureCollection")
    requested = set(map(str, codes))
    if not requested:
        raise ValueError("Municipality scope must not be empty")
    found, shapes = set(), []
    for feature in geojson["features"]:
        code = str(feature["properties"].get("codarea"))
        if code not in requested:
            continue
        geom = shape(feature["geometry"])
        if geom.geom_type not in {"Polygon", "MultiPolygon"} or geom.is_empty or not geom.is_valid:
            raise ValueError(f"Invalid municipality geometry: {code}; no automatic repair")
        found.add(code)
        shapes.append(geom)
    if requested != found:
        raise ValueError(f"Municipalities missing from GeoJSON: {sorted(requested-found)}")
    region = unary_union(shapes)
    if region.is_empty or not region.is_valid:
        raise ValueError("Invalid municipal union")
    return region, sorted(requested)

def _review_records(reviews):
    if reviews is None or reviews.empty:
        return {}
    if reviews.columns.has_duplicates:
        raise ValueError("Duplicate review column names")
    reviews = reviews.copy()
    for original, alias in [(PREFIX, "prefix"), (LAT, "lat"), (LNG, "lng")]:
        if original in reviews and alias in reviews:
            raise ValueError("Ambiguous review column names")
        if original not in reviews and alias in reviews:
            reviews = reviews.rename(columns={alias: original})
    required = {"source_row_number", PREFIX, LAT, LNG, "decision", "reason"}
    if not required.issubset(reviews.columns):
        raise ValueError(f"Missing review columns: {sorted(required-set(reviews.columns))}")
    out = {}
    for record in reviews.to_dict("records"):
        number = float(record["source_row_number"])
        if not np.isfinite(number) or not number.is_integer() or number < 2:
            raise ValueError("Review source_row_number must be an integer >= 2")
        number = int(number)
        if number in out:
            raise ValueError("Duplicate review")
        if record["decision"] not in {"exclude_outside_region", "retain_boundary_uncertainty"}:
            raise ValueError("Invalid review decision")
        if pd.isna(record["reason"]) or not str(record["reason"]).strip():
            raise ValueError("A documented review reason is required")
        out[number] = record
    return out

def validate_geolocation(full_geo, requested_prefixes, geojson, municipality_codes, review_decisions=None):
    """Return (retained raw rows, audit rows, summary).

    City/state text does not determine exclusion. Covers includes boundaries.
    Every valid point outside the union requires a reviewed original record.
    Distances in EPSG:31983 are descriptive, never an exclusion threshold.
    Duplicate source observations remain in the arithmetic mean. Read persisted
    review floats with float_precision='round_trip' for exact source matching.
    """
    if full_geo.columns.has_duplicates:
        raise ValueError("Duplicate source column names")
    if not {PREFIX, LAT, LNG}.issubset(full_geo.columns):
        raise ValueError("Missing source coordinate columns")
    reserved = {"source_row_number", "status", "decision", "reason", "distance_to_region_km"}
    if reserved.intersection(full_geo.columns):
        raise ValueError("Source contains reserved audit columns")
    requested = {_prefix_key(p) for p in requested_prefixes}
    if None in requested:
        raise ValueError("Invalid requested five-digit prefix")
    region, codes = _load_region(geojson, municipality_codes)
    reviews = _review_records(review_decisions)
    source_columns = list(full_geo.columns)
    source = full_geo.copy()
    source["source_row_number"] = np.arange(len(source), dtype=np.int64) + 2
    target = source[source[PREFIX].map(_prefix_key).isin(requested)].copy().reset_index(drop=True)
    keys = target[PREFIX].map(_prefix_key).to_numpy()
    lat = pd.to_numeric(target[LAT], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    lng = pd.to_numeric(target[LNG], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    valid = np.isfinite(lat) & np.isfinite(lng) & (abs(lat) <= 90) & (abs(lng) <= 180)
    inside = np.zeros(len(target), dtype=bool)
    shapely.prepare(region)
    inside[valid] = shapely.covers(region, shapely.points(lng[valid], lat[valid]))
    outside = valid & ~inside
    outside_ids = set(target.loc[outside, "source_row_number"].astype(int))
    if outside_ids - set(reviews):
        raise ValueError(f"Missing reviewed decisions: {sorted(outside_ids-set(reviews))}")
    if set(reviews) - outside_ids:
        raise ValueError("Reviews do not correspond to outside target rows")
    audit = target.copy()
    audit["status"] = np.where(valid, np.where(inside, "inside_region", "outside_region"), "invalid_coordinates")
    audit["decision"] = np.where(inside, "retain_inside_region", "exclude_invalid_coordinates")
    audit["reason"] = np.where(inside, "covered_by_selected_municipal_union", "non_numeric_non_finite_or_out_of_global_bounds")
    distances = np.full(len(target), np.nan)
    distances[inside] = 0
    if outside.any():
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
        projected = transform(transformer.transform, region)
        x, y = transformer.transform(lng[outside], lat[outside])
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Cannot project coordinates for audit")
        distances[outside] = shapely.distance(projected, shapely.points(x, y)) / 1000
    audit["distance_to_region_km"] = distances
    for position in np.flatnonzero(outside):
        number = int(target.iloc[position].source_row_number)
        record = reviews[number]
        if (_prefix_key(record[PREFIX]) != keys[position] or
                float(record[LAT]) != lat[position] or float(record[LNG]) != lng[position]):
            raise ValueError(f"Source mismatch in review for row {number}")
        audit.at[position, "decision"] = record["decision"]
        audit.at[position, "reason"] = str(record["reason"]).strip()
    retained = inside | audit.decision.eq("retain_boundary_uncertainty").to_numpy()
    clean = target[retained].copy()
    clean[LAT], clean[LNG] = lat[retained], lng[retained]
    clean = clean.reset_index(drop=True)
    retained_prefixes = set(clean[PREFIX].map(_prefix_key))
    summary = {
        "input_rows": len(full_geo), "target_rows": len(target),
        "requested_prefix_count": len(requested), "target_prefix_count": len(set(keys)),
        "retained_rows": int(retained.sum()), "excluded_rows": int((~retained).sum()),
        "inside_region_rows": int(inside.sum()), "outside_region_rows": int(outside.sum()),
        "invalid_coordinate_rows": int((~valid).sum()),
        "excluded_outside_region_rows": int(audit.decision.eq("exclude_outside_region").sum()),
        "retained_boundary_uncertainty_rows": int(audit.decision.eq("retain_boundary_uncertainty").sum()),
        "retained_prefix_count": len(retained_prefixes),
        "prefixes_without_retained_coordinates": sorted(requested-retained_prefixes),
        "duplicate_geo_rows_in_target": int(target.duplicated(subset=source_columns, keep=False).sum()),
        "duplicate_geo_rows_after_first_in_target": int(target.duplicated(subset=source_columns).sum()),
        "duplicate_geo_rows_after_first_retained": int(clean.duplicated(subset=source_columns).sum()),
        "duplicates_preserved": True, "municipality_codes": codes, "geometry_predicate": "covers",
        "distance_audit_crs": "EPSG:31983", "automatic_outside_exclusion": False,
    }
    return clean, audit, summary

def audit_aggregated_coordinates(aggregated, geojson, municipality_codes):
    """Flag derived averages outside the union; never remove source demand."""
    region, _ = _load_region(geojson, municipality_codes)
    flagged = aggregated.copy()
    flagged["mean_inside_region"] = shapely.covers(
        region, shapely.points(flagged["lng"].to_numpy(), flagged["lat"].to_numpy()))
    flagged["audit_reason"] = np.where(flagged["mean_inside_region"],
        "derived_mean_inside_region", "derived_mean_outside_region_not_an_address")
    return flagged
