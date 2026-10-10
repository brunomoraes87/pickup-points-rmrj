"""Deterministic facility candidates; demand rows and their weights are never removed."""
from pathlib import Path
import json
import numpy as np
import pandas as pd


def prefix_column(df):
    """Return the postal-prefix column used by the demand frame."""
    if "CEP" in df.columns:
        return "CEP"
    if "customer_zip_code_prefix" in df.columns:
        return "customer_zip_code_prefix"
    raise ValueError("Demand needs CEP or customer_zip_code_prefix")


def normalized_prefixes(df):
    values = df[prefix_column(df)]
    if values.isna().any():
        raise ValueError("Postal prefixes cannot be missing")
    def normalize(value):
        text = str(value).strip()
        if text.endswith(".0") and text[:-2].isdigit():
            text = text[:-2]
        if not text:
            raise ValueError("Postal prefixes cannot be empty")
        return text.zfill(5) if text.isdigit() else text
    return values.map(normalize).to_numpy(dtype=str)


def select_candidate_indices(df, n_candidates=None, tie_order="ascending", eligible_mask=None):
    """Return integer row POSITIONS sorted by demand DESC and prefix ASC/DESC.

    The input index labels are deliberately ignored. None selects all eligible
    positions in that same ordering. Eligibility applies only to candidate
    facilities, never to the demand rows, order counts or evaluation denominator.
    With the ascending-prefix v21 input, ascending reproduces nlargest(300)
    exactly, including the order of candidates tied at the cutoff.
    """
    if tie_order not in ("ascending", "descending"):
        raise ValueError("tie_order must be ascending or descending")
    if n_candidates is not None and (
            not isinstance(n_candidates, (int, np.integer)) or n_candidates <= 0):
        raise ValueError("n_candidates must be a positive integer or None")
    if "n_pedidos" not in df:
        raise ValueError("Demand needs n_pedidos")
    weights = pd.to_numeric(df.n_pedidos, errors="raise").to_numpy(dtype=float)
    if not np.isfinite(weights).all() or (weights <= 0).any() or (weights != np.floor(weights)).any():
        raise ValueError("Order counts must be positive finite integers")
    prefixes = normalized_prefixes(df)
    if len(set(prefixes)) != len(prefixes):
        raise ValueError("Postal prefixes must be unique")
    if eligible_mask is None:
        eligible = np.ones(len(df), dtype=bool)
    else:
        eligible = np.asarray(eligible_mask)
        if eligible.dtype.kind != "b" or eligible.shape != (len(df),):
            raise ValueError("eligible_mask must be one boolean per demand position")
    positions = np.flatnonzero(eligible)
    frame = pd.DataFrame({"position": positions, "weight": weights[positions],
                          "prefix": prefixes[positions]})
    ordered = frame.sort_values(
        ["weight", "prefix", "position"],
        ascending=[False, tie_order == "ascending", True], kind="mergesort")
    if n_candidates is not None:
        ordered = ordered.head(n_candidates)
    return ordered.position.to_numpy(dtype=np.int64)


def load_municipal_union(geojson_path, scope_path):
    """The administrative union is an eligibility proxy, not a water/land mask."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    scope = json.loads(Path(scope_path).read_text(encoding="utf-8-sig"))
    geojson = json.loads(Path(geojson_path).read_text(encoding="utf-8-sig"))
    codes = set(map(str, scope["municipality_codes"]))
    features = [f for f in geojson["features"] if str(f["properties"]["codarea"]) in codes]
    if {str(f["properties"]["codarea"]) for f in features} != codes:
        raise ValueError("The geometry does not contain every scoped municipality")
    return unary_union([shape(f["geometry"]) for f in features])


def inside_union_mask(coords, union):
    import shapely
    coords = np.asarray(coords, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2 or not np.isfinite(coords).all():
        raise ValueError("Finite latitude/longitude pairs required")
    return np.asarray(shapely.covers(union, shapely.points(coords[:, 1], coords[:, 0])), dtype=bool)


def postal_candidates(df, positions=None, union=None):
    """Candidate records retain the source demand POSITION for provenance."""
    positions = (np.arange(len(df), dtype=np.int64) if positions is None
                 else np.asarray(positions, dtype=np.int64))
    if positions.ndim != 1 or len(np.unique(positions)) != len(positions):
        raise ValueError("Candidate positions must be a unique one-dimensional array")
    if ((positions < 0) | (positions >= len(df))).any():
        raise ValueError("Candidate position outside demand")
    coords = df[["lat", "lng"]].to_numpy(dtype=float)[positions]
    prefixes = normalized_prefixes(df)[positions]
    frame = pd.DataFrame({
        "candidate_id": ["postal_" + p for p in prefixes],
        "source_kind": "postal_mean", "source_position": positions,
        "postal_prefix": prefixes, "lat": coords[:, 0], "lng": coords[:, 1],
    })
    frame["inside_union"] = (inside_union_mask(coords, union) if union is not None
                             else pd.array([pd.NA] * len(frame), dtype="boolean"))
    return frame


def grid_candidates(df, union, step_m, filter_postal=False, margin_m=3000):
    """Reproduce the finite 1 km / 500 m grids from the audited definition.

    Grid points are inside the administrative union. When filter_postal is
    false, all postal means are appended even if outside it; this is explicitly
    marked. Filtering removes candidate facilities only, keeping all demand.
    These sets do not establish the optimum over continuous eligible terrain.
    """
    from pyproj import Transformer
    if not np.isfinite(step_m) or step_m <= 0 or not np.isfinite(margin_m) or margin_m < 0:
        raise ValueError("Positive step and nonnegative finite margin required")
    coords = df[["lat", "lng"]].to_numpy(dtype=float)
    if not len(coords) or not np.isfinite(coords).all():
        raise ValueError("Finite nonempty demand coordinates required")
    forward = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
    inverse = Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True)
    x, y = forward.transform(coords[:, 1], coords[:, 0])
    xx, yy = np.meshgrid(np.arange(x.min()-margin_m, x.max()+margin_m, step_m),
                         np.arange(y.min()-margin_m, y.max()+margin_m, step_m))
    lng, lat = inverse.transform(xx.ravel(), yy.ravel())
    grid_coords = np.column_stack([lat, lng])
    keep = inside_union_mask(grid_coords, union)
    grid_positions = np.flatnonzero(keep)
    grid = pd.DataFrame({
        "candidate_id": [f"grid_{step_m:g}_{i}" for i in grid_positions],
        "source_kind": "municipal_grid", "source_position": grid_positions,
        "postal_prefix": None, "lat": grid_coords[keep, 0], "lng": grid_coords[keep, 1],
        "inside_union": True,
    })
    postal = postal_candidates(df, union=union)
    postal_outside = int((~postal.inside_union).sum())
    if filter_postal:
        postal = postal[postal.inside_union].copy()
    frame = pd.concat([postal, grid], ignore_index=True)
    metadata = {
        "step_m": float(step_m), "margin_m": float(margin_m),
        "origin_x": float(x.min()-margin_m), "origin_y": float(y.min()-margin_m),
        "grid_points": len(grid), "postal_candidates": len(postal),
        "postal_outside_before_filter": postal_outside,
        "postal_filtered": bool(filter_postal), "candidate_count": len(frame),
        "eligible_area": "administrative municipal union; not a physical/commercial land mask",
        "scope": "finite candidate set only; no continuous optimality certificate",
    }
    return frame, metadata
