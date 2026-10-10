"""Declared v22 sensitivity analyses, with independent distance/coverage metrics.

The main v21 cohort is immutable. Administrative geometry does not certify
dry land, a commercial property, a route, or an individual order address.
"""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import time
import unicodedata
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
import shapely
from shapely.geometry import shape, LineString
from shapely.ops import unary_union, transform
from sklearn.cluster import AgglomerativeClustering, KMeans
from candidate_sets import select_candidate_indices, inside_union_mask
from methods import method_pmedian_heuristic

EARTH_KM = 6371.0088
RADII = (3, 5, 10)
SEEDS = (42, 0, 1, 2, 3)
METHODS = ("K-Means", "Ward", "Complete", "Average", "P-Median", "MCLP")
DISCRETE = ("P-Median", "MCLP")
KM_CONFIG = dict(init="k-means++", n_init=10, max_iter=300,
                 tol=1e-4, algorithm="lloyd")
GEOD = Geod(ellps="WGS84")
FORWARD = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
INVERSE = Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True)
LOCK_DELAYS = (.05, .1, .2, .4, .8)
POLICY = {
    "main": "v21 immutable N9691; mean with repeated records; angular K-Means/Ward; J300 demand DESC prefix ASC",
    "coverage": "nearest represented postal center; distance <= R; covered integer orders >= ceil(.95*N)",
    "quantiles": "empirical inverse CDF over order counts, ceil(q*N), no interpolation",
    "search": "every integer K from 1; first simultaneous five-seed feasible K; no monotonicity assumption",
    "geography": "administrative municipal union; no water, terrain or commercial validity claim",
    "redistribution": "hypothesis only: equal fractional order weight among retained records of each prefix; not individual addresses",
    "omissions": "D16 strict record majority; D22 includes six ties; exploratory not validated recovery",
    "comparison": "overlapping K intervals imply absence of robust descriptive separation, not statistical equivalence",
    "pmedian": "same greedy construction, candidate order, first-improvement swaps, eps1e-9, max_iter100",
    "timing": "descriptive wall clock, excludes metrics/export; cached fit time retained; not a controlled CPU comparison",
}

def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).strip().lower())
                   if not unicodedata.combining(c))

def prefix_series(values):
    def one(v):
        s = str(v).strip()
        if s.endswith(".0") and s[:-2].isdigit():
            s = s[:-2]
        return s.zfill(5)
    return values.map(one)

def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def object_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def array_sha(values):
    a = np.ascontiguousarray(values)
    return hashlib.sha256(a.dtype.str.encode() + str(a.shape).encode() + a.tobytes()).hexdigest()

def replace_retry(source, target):
    """Windows readers can momentarily lock a destination; other errors propagate."""
    for attempt in range(len(LOCK_DELAYS) + 1):
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            locked = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in (32, 33)
            if not locked or attempt == len(LOCK_DELAYS):
                raise
            time.sleep(LOCK_DELAYS[attempt])

def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
                   encoding="utf-8")
    replace_retry(tmp, path)

def atomic_csv(path, frame):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    frame.to_csv(tmp, index=False, encoding="utf-8", float_format="%.17g")
    replace_retry(tmp, path)

def atomic_npz(path, **values):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as f:
        np.savez_compressed(f, **values)
    replace_retry(tmp, path)

def distances(coords, centers, metric="haversine"):
    """Own evaluation; arrays are latitude/longitude, distance in kilometers."""
    a = np.asarray(coords, float); b = np.asarray(centers, float)
    if not len(b):
        return np.full((len(a), 0), np.inf)
    if metric == "geodesic":
        la, lb = np.broadcast_arrays(a[:, 0, None], b[None, :, 0])
        loa, lob = np.broadcast_arrays(a[:, 1, None], b[None, :, 1])
        return GEOD.inv(loa.ravel(), la.ravel(), lob.ravel(), lb.ravel())[2].reshape(la.shape) / 1000
    if metric != "haversine":
        raise ValueError("Unknown distance metric")
    la = np.radians(a[:, 0, None]); lb = np.radians(b[None, :, 0])
    dlo = np.radians(b[None, :, 1]) - np.radians(a[:, 1, None])
    dla = lb - la
    h = np.sin(dla / 2)**2 + np.cos(la) * np.cos(lb) * np.sin(dlo / 2)**2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(h, 0, 1)))

def inverse_cdf(d, weights, q):
    weights = np.asarray(weights)
    if np.any(weights <= 0) or not np.array_equal(weights, weights.astype(np.int64)):
        raise ValueError("Positive integer order counts required")
    rank = max(1, math.ceil(float(q) * int(weights.sum())))
    ix = np.argsort(d, kind="stable")
    return float(np.asarray(d)[ix[np.searchsorted(np.cumsum(weights[ix]), rank, side="left")]])

def required_orders(weights):
    return math.ceil(.95 * int(np.asarray(weights).sum()))

def metrics_from_distances(d, weights, radius):
    d = np.asarray(d, float); w = np.asarray(weights, np.int64)
    total = int(w.sum()); covered = int(w[d <= radius].sum())
    if not len(d) or not np.isfinite(d).all():
        raise ValueError("Finite nonempty nearest distances required")
    return dict(N_orders=total, required_orders=required_orders(w),
                covered_orders=covered, uncovered_orders=total - covered,
                coverage_pct=100 * covered / total,
                feasible=covered >= required_orders(w),
                coverage_margin_orders=covered - required_orders(w),
                weighted_mean_km=float(np.average(d, weights=w)),
                p95_km=inverse_cdf(d, w, .95),
                p99_km=inverse_cdf(d, w, .99), max_km=float(d.max()))

def evaluate_fit(df, labels, centers, radius, metric="haversine"):
    D = distances(df[["lat", "lng"]].to_numpy(), centers, metric)
    nearest = D.argmin(axis=1); d = D[np.arange(len(df)), nearest]
    labels = np.asarray(labels, dtype=int)
    native = D[np.arange(len(df)), labels]
    result = metrics_from_distances(d, df.n_pedidos.to_numpy(), radius)
    changed = labels != nearest
    result.update(native_max_km=float(native.max()),
                  reassigned_prefixes=int(changed.sum()),
                  reassigned_orders=int(df.n_pedidos.to_numpy()[changed].sum()))
    return result, d, nearest, native

def first_feasible_integer(rows, seeds=SEEDS):
    """Require every declared seed at the same integer, regardless of reversals."""
    grouped = {}
    for row in rows:
        grouped.setdefault(int(row["K"]), {})[int(row["seed"])] = bool(row["feasible"])
    for k in sorted(grouped):
        if set(seeds).issubset(grouped[k]) and all(grouped[k][s] for s in seeds):
            return k
    return None

def weighted_centers(coords, weights, labels):
    centers = []
    for c in np.unique(labels):
        m = labels == c
        w = np.asarray(weights[m], float); w = w / w.sum()
        centers.append((np.average(coords[m, 0], weights=w), np.average(coords[m, 1], weights=w)))
    return np.asarray(centers)

@dataclass
class Cohort:
    name: str
    df: pd.DataFrame
    orders: pd.DataFrame
    records: pd.DataFrame
    note: str = ""
    estimator: str = "mean_repeated"

@dataclass
class Case:
    name: str
    cohort: Cohort
    metric: str = "haversine"
    fit_space: str = "angular"
    center_mode: str = "native"
    candidates: np.ndarray | None = None
    methods: tuple = METHODS
    note: str = ""
    fit_metric: str | None = None

def adjustment_metric(case, method):
    if method in ("K-Means", "Ward"):
        return "euclidean_EPSG31983_m" if case.fit_space == "projected" else "euclidean_degrees"
    return case.fit_metric or case.metric

def load_geometry(data_dir):
    folder = Path(data_dir) / "geography"
    scope = json.loads((folder / "scope.json").read_text(encoding="utf-8-sig"))
    blob = json.loads((folder / "rj_municipios_ibge.geojson").read_text(encoding="utf-8-sig"))
    codes = set(map(str, scope["municipality_codes"]))
    polygons = {normalize(scope["municipalities"][str(f["properties"]["codarea"])]): shape(f["geometry"])
                for f in blob["features"] if str(f["properties"]["codarea"]) in codes}
    if len(polygons) != len(codes):
        raise ValueError("Incomplete scoped geometry")
    return unary_union(list(polygons.values())), polygons, scope

def read_prefix_csv(path, column):
    df = pd.read_csv(path, dtype={column: str})
    df[column] = prefix_series(df[column])
    return df

def estimator_frame(main, records, estimator):
    fields = ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
              "geolocation_city", "geolocation_state"]
    src = records.drop_duplicates(fields) if estimator == "dedup_full" else records
    grouped = src.groupby("CEP")[["lat", "lng"]]
    centers = grouped.median() if estimator == "median" else grouped.mean()
    result = main.copy()
    result[["lat", "lng"]] = centers.loc[result.CEP, ["lat", "lng"]].to_numpy()
    return result

def add_hypothetical_orders(main, orders, records, omitted, name):
    """Keep existing coordinates; add counts. New means use internal raw records only."""
    extra = omitted.copy()
    extra["municipality_for_sensitivity"] = extra["municipio_inferido"]
    extra["municipality_origin"] = "inferencia_prefixo_omisso"
    extra["city_norm"] = extra["municipio_original"]
    combined = pd.concat([orders, extra[orders.columns]], ignore_index=True)
    if combined.order_id.duplicated().any():
        raise ValueError("Order multiplication in omission scenario")
    frame = main.copy()
    counts = combined.groupby("CEP").size()
    existing = set(frame.CEP)
    frame["n_pedidos"] = frame.CEP.map(counts).astype(np.int64)
    additions = []
    for cep in counts.index.difference(frame.CEP):
        group = extra[extra.CEP == cep]
        # The inferred coordinates are explicitly conditional on internal raw records.
        row = dict(CEP=cep, lat=float(group.iloc[0].lat),
                   lng=float(group.iloc[0].lng),
                   n_pedidos=int(counts[cep]),
                   city_norm=group.iloc[0].municipio_original)
        additions.append(row)
    if additions:
        frame = pd.concat([frame, pd.DataFrame(additions)], ignore_index=True)
    frame = frame.sort_values("CEP", kind="stable").reset_index(drop=True)
    if not np.array_equal(frame.set_index("CEP").loc[main.CEP, ["lat", "lng"]].to_numpy(),
                          main[["lat", "lng"]].to_numpy()):
        raise AssertionError("Existing coordinates changed")
    if int(frame.n_pedidos.sum()) != len(combined):
        raise AssertionError("Order denominator changed incorrectly")
    r = records.copy()
    return Cohort(name, frame, combined, r,
                  "Exploratory inference, not validated individual addresses; existing means preserved")

def load_inputs(raw_dir, data_dir):
    raw_dir = Path(raw_dir); data_dir = Path(data_dir)
    union, polygons, scope = load_geometry(data_dir)
    main = read_prefix_csv(data_dir / "demanda_por_cep.csv", "customer_zip_code_prefix")
    main = main.rename(columns={"customer_zip_code_prefix": "CEP"})
    main["n_pedidos"] = main.n_pedidos.astype(np.int64)
    orders = read_prefix_csv(data_dir / "pedidos_rmrj_geo.csv", "customer_zip_code_prefix")
    orders = orders.rename(columns={"customer_zip_code_prefix": "CEP"})
    customer = read_prefix_csv(raw_dir / "olist_customers_dataset.csv", "customer_zip_code_prefix")
    customer["municipio_original"] = customer.customer_city
    customer["cn"] = customer.customer_city.map(normalize)
    all_orders = pd.read_csv(raw_dir / "olist_orders_dataset.csv")
    base_join = orders[["order_id", "customer_id", "CEP", "city_norm"]].merge(
        customer[["customer_id", "customer_unique_id", "municipio_original"]],
        on="customer_id", how="left", validate="many_to_one")
    base_join["municipality_for_sensitivity"] = base_join.city_norm
    base_join["municipality_origin"] = "cadastro_principal"
    order_columns = ["order_id", "customer_id", "customer_unique_id", "CEP", "city_norm",
                     "municipio_original", "municipality_for_sensitivity", "municipality_origin"]
    orders = base_join[order_columns]
    if len(orders) != int(main.n_pedidos.sum()) or orders.order_id.duplicated().any():
        raise ValueError("Main cohort order conservation failed")
    if not orders.groupby("CEP").size().reindex(main.CEP).equals(
            pd.Series(main.n_pedidos.to_numpy(), index=pd.Index(main.CEP, name="CEP"))):
        raise ValueError("Main prefix order counts inconsistent")
    geo = read_prefix_csv(raw_dir / "olist_geolocation_dataset.csv", "geolocation_zip_code_prefix")
    geo["source_row_number"] = np.arange(len(geo)) + 2
    geo["CEP"] = geo.geolocation_zip_code_prefix
    geo["lat"] = geo.geolocation_lat; geo["lng"] = geo.geolocation_lng
    valid = np.isfinite(geo[["lat", "lng"]].to_numpy()).all(axis=1)
    valid &= geo.lat.abs().le(90).to_numpy() & geo.lng.abs().le(180).to_numpy()
    inside = np.zeros(len(geo), bool)
    inside[valid] = inside_union_mask(geo.loc[valid, ["lat", "lng"]].to_numpy(), union)
    geo["inside_union"] = inside
    decisions = pd.read_csv(data_dir / "geography" / "geolocation_review_decisions.csv")
    retained_rows = decisions.loc[decisions.decision.eq("retain_boundary_uncertainty"),
                                 "source_row_number"].to_numpy()
    # Review references are required to point to the exact unchanged raw coordinates.
    check = geo.set_index("source_row_number").loc[decisions.source_row_number]
    for raw_field in ["geolocation_lat", "geolocation_lng"]:
        if not np.allclose(check[raw_field].to_numpy(), decisions[raw_field].to_numpy(), rtol=0, atol=1e-12):
            raise ValueError("Review source-row coordinates differ from raw input")
    for raw_field in ["geolocation_zip_code_prefix", "geolocation_city", "geolocation_state"]:
        left = check[raw_field].reset_index(drop=True).astype(str)
        right = decisions[raw_field].reset_index(drop=True).astype(str)
        if raw_field == "geolocation_zip_code_prefix":
            right = prefix_series(right)
        if not np.array_equal(left.to_numpy(), right.to_numpy()):
            raise ValueError("Review source-row postal/text identity differs from raw input")
    retained = geo[valid & (inside | geo.source_row_number.isin(retained_rows).to_numpy())]
    retained = retained[retained.CEP.isin(main.CEP)].copy()
    means = retained.groupby("CEP")[["lat", "lng"]].mean().loc[main.CEP].to_numpy()
    if not np.allclose(means, main[["lat", "lng"]].to_numpy(), rtol=0, atol=1e-11):
        raise ValueError("Retained raw records do not reproduce the main postal means")
    delivered = all_orders[all_orders.order_status.eq("delivered")].merge(
        customer, on="customer_id", validate="many_to_one")
    omitted_pool = delivered[delivered.customer_state.eq("RJ") & ~delivered.cn.isin(polygons)]
    omitted_pool = omitted_pool[~omitted_pool.order_id.isin(orders.order_id)].copy()
    omission_rows = []
    extra_record_frames = []
    for cep, group in omitted_pool.groupby("customer_zip_code_prefix", sort=True):
        all_r = geo[geo.CEP.eq(cep)]
        internal = all_r[all_r.inside_union]
        share = len(internal) / len(all_r) if len(all_r) else 0
        if share < .5 or not len(internal):
            continue
        lat = float(internal.lat.mean()); lng = float(internal.lng.mean())
        p = shapely.Point(lng, lat)
        names = [name for name, poly in polygons.items() if poly.covers(p)]
        inferred = names[0] if len(names) == 1 else "|".join(names)
        for row in group.to_dict("records"):
            omission_rows.append(dict(
                order_id=row["order_id"], customer_id=row["customer_id"],
                customer_unique_id=row["customer_unique_id"], CEP=cep,
                city_norm=row["cn"], municipio_original=row["customer_city"],
                municipio_inferido=inferred, lat=lat, lng=lng,
                n_all=len(all_r), n_inside=len(internal), share_inside=share,
                strict_majority=share > .5, geographic_tie=share == .5,
                criterion="record_share_inside > .5" if share > .5 else "record_share_inside == .5",
                decision="exploratory_only_not_recovered",
                municipality_for_sensitivity=inferred,
                municipality_origin="inferencia_prefixo_omisso"))
        extra_record_frames.append(internal)
    omitted = pd.DataFrame(omission_rows)
    if omitted.empty:
        raise ValueError("No omission-hypothesis inputs found")
    full_records = pd.concat([retained, *extra_record_frames], ignore_index=True).drop_duplicates("source_row_number")
    cohort = Cohort("main", main, orders, retained)
    d16 = add_hypothetical_orders(main, orders, full_records, omitted[omitted.strict_majority], "D16")
    d22 = add_hypothetical_orders(main, orders, full_records, omitted, "D22")
    if (len(main), len(orders), len(d16.orders), len(d22.orders)) != (828, 9691, 9707, 9713):
        raise ValueError("Protocol cohort counts changed; review rather than silently proceeding")
    return cohort, d16, d22, omitted, union, polygons, scope

def make_cases(main, d16, d22, union):
    j300 = select_candidate_indices(main.df, 300)
    legacy = main.df.nlargest(300, "n_pedidos").index.to_numpy()
    if not np.array_equal(j300, legacy):
        raise ValueError("Explicit J300 does not reproduce v21 legacy ordering")
    cases = [Case("main", main, candidates=j300),
             Case("geodesic", main, metric="geodesic", candidates=j300),
             Case("geodesic_eval_only", main, metric="geodesic", fit_metric="haversine", candidates=j300,
                  note="Reviewer sensitivity: adjustment unchanged; WGS84 evaluation only")]
    for estimator in ("median", "dedup_full"):
        frame = estimator_frame(main.df, main.records, estimator)
        co = Cohort("main", frame, main.orders, main.records,
                    "Same immutable main order cohort", estimator)
        cases.append(Case(estimator, co, candidates=select_candidate_indices(frame, 300)))
    cases.extend([
        Case("projected_inverse", main, fit_space="projected", center_mode="inverse",
             candidates=j300, methods=("K-Means", "Ward")),
        Case("projected_partition_angular", main, fit_space="projected", center_mode="angular_mean",
             candidates=j300, methods=("K-Means", "Ward")),
        Case("J_all828", main, candidates=select_candidate_indices(main.df), methods=DISCRETE),
        Case("J_union825", main, candidates=select_candidate_indices(
            main.df, eligible_mask=inside_union_mask(main.df[["lat", "lng"]].to_numpy(), union)),
            methods=DISCRETE, note="Only facilities filtered; all demand and N preserved"),
        Case("J300_tie_reverse", main, candidates=select_candidate_indices(main.df, 300, "descending"),
             methods=DISCRETE),
        Case("J_all828_legacy_order", main, candidates=np.arange(len(main.df)), methods=DISCRETE,
             note="Legacy original prefix ASC order; same full candidate set"),
        Case("J_union825_legacy_order", main, candidates=np.flatnonzero(
            inside_union_mask(main.df[["lat", "lng"]].to_numpy(), union)), methods=DISCRETE,
             note="Original prefix ASC order filtered to union; all demand preserved")])
    fixed_prefixes = main.df.CEP.iloc[j300].to_list()
    for co in (d16, d22):
        jnew = select_candidate_indices(co.df, 300)
        cases.append(Case(co.name, co, candidates=jnew,
                          note="Changed demand denominator AND recalculated top300 candidates"))
        mapping = {p: i for i, p in enumerate(co.df.CEP)}
        jfixed = np.asarray([mapping[p] for p in fixed_prefixes])
        cases.append(Case(co.name + "_main300fixed", co, candidates=jfixed, methods=DISCRETE,
                          note="Paired demand-only change with main top300 identities and order fixed"))
    return cases

class FitStore:
    def __init__(self, out, code_signature):
        self.folder = Path(out) / "checkpoints"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.code_signature = code_signature

    def key(self, config):
        return object_sha(dict(code=self.code_signature, **config))

    def get(self, key):
        path = self.folder / (key + ".npz")
        if not path.exists():
            return None
        with np.load(path, allow_pickle=False) as z:
            return (z["labels"], z["centers"], float(z["runtime_s"]),
                    json.loads(str(z["diagnostics"].item())))

    def put(self, key, result):
        labels, centers, runtime, diag = result
        atomic_npz(self.folder / (key + ".npz"), labels=labels, centers=centers,
                   runtime_s=np.asarray(runtime),
                   diagnostics=np.asarray(json.dumps(diag, sort_keys=True)))

    def trajectory(self, case, D, radius):
        weights = case.cohort.df.n_pedidos.to_numpy(float)
        idx = case.candidates
        config = dict(kind="mclp_trajectory", matrix=array_sha(D), weights=array_sha(weights),
                      candidates=idx.tolist(), radius=radius)
        key = self.key(config); path = self.folder / (key + ".npz")
        if path.exists():
            with np.load(path, allow_pickle=False) as z:
                return z["selected"], z["cumulative_s"], key
        selected, elapsed = greedy_trajectory(D[:, idx], weights, radius)
        selected = idx[selected]
        atomic_npz(path, selected=selected, cumulative_s=elapsed)
        return selected, elapsed, key

def greedy_trajectory(D, weights, radius):
    """Exact original max-gain/first-tie order; prefixes equal independent p fits."""
    covers = D <= radius
    available = list(range(D.shape[1])); selected = []
    covered = np.zeros(len(weights), bool); elapsed = []
    t0 = time.perf_counter()
    while available:
        best_j = None; best_gain = -1
        for j in available:
            gain = float(np.asarray(weights)[covers[:, j] & ~covered].sum())
            if gain > best_gain:
                best_gain, best_j = gain, j
        if best_j is None or best_gain <= 0:
            break
        selected.append(best_j); covered |= covers[:, best_j]; available.remove(best_j)
        elapsed.append(time.perf_counter() - t0)
    return np.asarray(selected, dtype=int), np.asarray(elapsed, float)

def fit_at_k(case, method, k, seed, D, store):
    df = case.cohort.df; coords = df[["lat", "lng"]].to_numpy(float)
    weights = df.n_pedidos.to_numpy(float)
    fit_metric = (case.fit_metric or case.metric) if method in ("Complete", "Average", "P-Median") else "no_distance_metric"
    config = dict(kind="fit", coordinates=array_sha(coords), weights=array_sha(weights),
                  method=method, K=k, seed=seed, fit_metric=fit_metric,
                  fit_space=case.fit_space if method in ("K-Means", "Ward") else "angular",
                  center_mode=case.center_mode if method in ("K-Means", "Ward") else "native",
                  candidates=case.candidates.tolist() if method == "P-Median" else [],
                  kmeans=KM_CONFIG if method == "K-Means" else {}, max_iter=100)
    key = store.key(config); cached = store.get(key)
    if cached is not None:
        return *cached, key
    t0 = time.perf_counter(); diag = {}
    if method == "P-Median":
        labels, centers, _, diag = method_pmedian_heuristic(
            df, k, case.candidates, max_iter=100, distance_matrix=D, return_diagnostics=True)
    else:
        fit_coords = coords
        if case.fit_space == "projected" and method in ("K-Means", "Ward"):
            x, y = FORWARD.transform(coords[:, 1], coords[:, 0])
            fit_coords = np.column_stack([x, y])
        if method == "K-Means":
            model = KMeans(n_clusters=k, random_state=seed, **KM_CONFIG)
            labels = model.fit_predict(fit_coords, sample_weight=weights)
            centers = model.cluster_centers_
            diag["kmeans_iterations"] = int(model.n_iter_)
        elif method in ("Ward", "Complete", "Average"):
            link = method.lower()
            labels = AgglomerativeClustering(
                n_clusters=k, linkage=link, metric="euclidean" if method == "Ward" else "precomputed"
            ).fit_predict(fit_coords if method == "Ward" else D)
            centers = weighted_centers(fit_coords, weights, labels)
        else:
            raise ValueError("Unsupported fit method")
        if case.fit_space == "projected" and method in ("K-Means", "Ward"):
            if case.center_mode == "inverse":
                lng, lat = INVERSE.transform(centers[:, 0], centers[:, 1])
                centers = np.column_stack([lat, lng])
            elif case.center_mode == "angular_mean":
                centers = weighted_centers(coords, weights, labels)
            else:
                raise ValueError("Projected center definition required")
    result = labels, centers, time.perf_counter() - t0, diag
    store.put(key, result)
    return *result, key

def candidate_audit(cases, main):
    base = set(main.df.CEP.iloc[select_candidate_indices(main.df, 300)])
    rows = []
    for case in cases:
        prefixes = case.cohort.df.CEP.iloc[case.candidates].to_list()
        selected = set(prefixes)
        rows.append(dict(case=case.name, cohort=case.cohort.name, N_orders=int(case.cohort.df.n_pedidos.sum()),
                         n_candidates=len(prefixes), ordered_prefixes_sha256=object_sha(prefixes),
                         evaluation_metric=case.metric, fit_metric_precomputed=case.fit_metric or case.metric,
                         fit_space=case.fit_space, candidate_order=(
                             "prefix_ascending_legacy" if "legacy_order" in case.name else
                             "main300fixed_original_order" if "main300fixed" in case.name else
                             "demand_desc_prefix_desc" if "tie_reverse" in case.name else "demand_desc_prefix_asc"),
                         entered_vs_main300="|".join(sorted(selected - base)),
                         exited_vs_main300="|".join(sorted(base - selected)), note=case.note))
    return pd.DataFrame(rows)

def conservative_comparison(selection, expected_variants, methods):
    """Do not classify incomplete variant comparisons or label overlap equivalence."""
    rows = []
    for radius in RADII:
        for i, a in enumerate(methods):
            for b in methods[i + 1:]:
                frame = selection[(selection.radius_km == radius) & selection.method.isin([a, b])
                                  & selection.case.isin(expected_variants)]
                have = set(zip(frame.case, frame.method))
                need = {(v, m) for v in expected_variants for m in (a, b)}
                usable = frame[frame.status.eq("selected")]
                if not need.issubset(have) or len(usable) != len(need):
                    rows.append(dict(radius_km=radius, method_a=a, method_b=b,
                                     classification="incomplete_variants_no_classification",
                                     statistical_claim="none"))
                    continue
                pivot = usable.pivot(index="case", columns="method", values="K_selected")
                amin, amax = int(pivot[a].min()), int(pivot[a].max())
                bmin, bmax = int(pivot[b].min()), int(pivot[b].max())
                overlap = max(amin, bmin) <= min(amax, bmax)
                same_sign = ((pivot[a] < pivot[b]).all() or (pivot[a] > pivot[b]).all())
                label = ("absence_of_robust_descriptive_separation" if overlap
                         else "stable_observed_order" if same_sign
                         else "order_changes_between_variants")
                rows.append(dict(radius_km=radius, method_a=a, method_b=b, a_min=amin, a_max=amax,
                                 b_min=bmin, b_max=bmax, classification=label,
                                 statistical_claim="none"))
    return pd.DataFrame(rows)


def municipal_metrics(orders, df, d, radius, municipality_names):
    lookup = dict(zip(df.CEP, np.asarray(d) <= radius))
    per_order = orders[["order_id", "CEP", "municipality_for_sensitivity", "municipality_origin"]].copy()
    per_order["covered"] = per_order.CEP.map(lookup)
    if per_order.covered.isna().any():
        raise ValueError("Municipal assignment lost orders")
    grouped = per_order.groupby("municipality_for_sensitivity").agg(
        N_orders=("order_id", "size"), covered_orders=("covered", "sum"))
    grouped = grouped.reindex(sorted(municipality_names), fill_value=0).reset_index()
    grouped = grouped.rename(columns={"municipality_for_sensitivity": "municipality"})
    grouped["covered_orders"] = grouped.covered_orders.astype(int)
    grouped["uncovered_orders"] = grouped.N_orders - grouped.covered_orders
    grouped["coverage_pct"] = np.where(grouped.N_orders > 0,
                                       100 * grouped.covered_orders / grouped.N_orders, np.nan)
    if int(grouped.N_orders.sum()) != len(orders):
        raise AssertionError("Municipal denominators not conserved")
    zero = grouped[(grouped.N_orders > 0) & (grouped.covered_orders == 0)]
    low = grouped[(grouped.N_orders > 0) & (grouped.coverage_pct < 80)]
    rio = grouped[grouped.municipality.eq("rio de janeiro")]
    uncovered = int(grouped.uncovered_orders.sum())
    rio_uncovered = int(rio.uncovered_orders.sum())
    summary = dict(municipalities_zero=int(len(zero)),
                   municipalities_below80=int(len(low)),
                   orders_in_zero_municipalities=int(zero.N_orders.sum()),
                   orders_in_below80_municipalities=int(low.N_orders.sum()),
                   uncovered_orders_in_below80_municipalities=int(low.uncovered_orders.sum()),
                   rio_uncovered_orders=rio_uncovered,
                   rio_share_of_uncovered_pct=100 * rio_uncovered / uncovered if uncovered else None,
                   inferred_municipality_orders=int(orders.municipality_origin.eq("inferencia_prefixo_omisso").sum()))
    return grouped, summary

def redistribution_metrics(records, df, centers, radius, metric="haversine"):
    """Equal fractional weights are a hypothesis, not new observed orders."""
    records = records[records.CEP.isin(df.CEP)].copy()
    counts = records.groupby("CEP").size()
    if not set(df.CEP).issubset(counts.index):
        raise ValueError("No retained records for some prefix")
    w = records.CEP.map(dict(zip(df.CEP, df.n_pedidos))).to_numpy(float)
    w /= records.CEP.map(counts).to_numpy(float)
    if not math.isclose(float(w.sum()), int(df.n_pedidos.sum()), rel_tol=0, abs_tol=1e-8):
        raise AssertionError("Fractional redistribution multiplied orders")
    nearest = distances(records[["lat", "lng"]].to_numpy(), centers, metric).min(axis=1)
    total = float(w.sum()); covered = float(w[nearest <= radius].sum())
    ix = np.argsort(nearest, kind="stable")
    c = np.cumsum(w[ix])
    def quantile(q):
        return float(nearest[ix[min(np.searchsorted(c, q * total), len(ix) - 1)]])
    return dict(redistributed_N_fractional=total,
                redistributed_covered_fractional=covered,
                redistributed_coverage_pct=100 * covered / total,
                redistributed_mean_km=float(np.average(nearest, weights=w)),
                redistributed_p95_km=quantile(.95), redistributed_p99_km=quantile(.99),
                redistributed_max_km=float(nearest.max()),
                redistribution_assumption="equal fractional weights by retained record; not actual addresses")

def geometry_flags(df, centers, nearest, union):
    coords = df[["lat", "lng"]].to_numpy(float)
    inside = inside_union_mask(centers, union)
    facility = pd.DataFrame({"facility_id": np.arange(len(centers)),
                             "lat": centers[:, 0], "lng": centers[:, 1],
                             "inside_municipal_union": inside,
                             "outside_municipal_union": ~inside})
    facility["nearest_assigned_orders"] = np.bincount(nearest, weights=df.n_pedidos,
                                                     minlength=len(centers)).astype(int)
    lines = shapely.linestrings(np.stack((coords[:, ::-1], centers[nearest, ::-1]), axis=1))
    external = shapely.difference(lines, union)
    def project_xy(xy):
        x, y = FORWARD.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([x, y])
    projected = shapely.transform(external, project_xy)
    lengths = shapely.length(projected) / 1000
    segments = pd.DataFrame({"CEP": df.CEP, "n_pedidos": df.n_pedidos,
                             "nearest_facility": nearest,
                             "external_union_segment_km_projected": lengths})
    return facility, segments, dict(
        outside_union_facilities=int((~inside).sum()),
        orders_nearest_to_outside_facilities=int(df.n_pedidos.to_numpy()[~inside[nearest]].sum()),
        orders_external_segment_gt2km=int(df.n_pedidos.to_numpy()[lengths > 2].sum()),
        geometry_interpretation="administrative union; external segment is not a water crossing or road route")

def prefix_diagnostics(main):
    rows = []; source_rows = []
    frame = main.df.set_index("CEP")
    full_fields = ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
                   "geolocation_city", "geolocation_state"]
    for cep, records in main.records.groupby("CEP", sort=True):
        mean = frame.loc[cep, ["lat", "lng"]].to_numpy(float)
        coords = records[["lat", "lng"]].to_numpy(float)
        d = distances(coords, mean.reshape(1, 2)).ravel()
        med = np.median(coords, axis=0)
        dedup = records.drop_duplicates(full_fields)[["lat", "lng"]].mean().to_numpy()
        extreme = d > 20
        rows.append(dict(CEP=cep, n_pedidos=int(frame.loc[cep].n_pedidos), n_records=len(records),
                         n_full_unique_records=len(records.drop_duplicates(full_fields)),
                         p50_record_to_mean_km=float(np.quantile(d, .5)),
                         p90_record_to_mean_km=float(np.quantile(d, .9)), max_record_to_mean_km=float(d.max()),
                         median_shift_km=float(distances(mean.reshape(1, 2), med.reshape(1, 2))[0, 0]),
                         dedup_full_shift_km=float(distances(mean.reshape(1, 2), dedup.reshape(1, 2))[0, 0]),
                         extreme_gt20km=bool(extreme.any()),
                         evidence_classification="inconsistency_not_proven_uncertain" if extreme.any() else "no_gt20km_flag",
                         action="retain_all_documented_records_no_arbitrary_exclusion"))
        for pos in np.flatnonzero(extreme):
            source = records.iloc[pos]
            source_rows.append(dict(CEP=cep, source_row_number=int(source.source_row_number),
                                    lat=source.lat, lng=source.lng,
                                    original_city=source.geolocation_city,
                                    original_state=source.geolocation_state,
                                    distance_to_postal_mean_km=float(d[pos]),
                                    inside_municipal_union=bool(source.inside_union),
                                    evidence="distance alone does not prove error; no individual address",
                                    classification="inconsistency_not_proven_uncertain", action="retain"))
    return pd.DataFrame(rows), pd.DataFrame(source_rows)

class SearchRunner:
    def __init__(self, out, signature, union, polygons):
        self.out = Path(out); self.store = FitStore(out, signature)
        self.union = union; self.polygons = polygons
        self.curves = []; self.selection = []; self.facilities = []
        self.municipal = []; self.network_summary = []; self.seed_first = []
        self.progress = []

    def persist(self):
        # Writes complete partial artifacts after every K; a lock never discards fits.
        for name, rows in (("sensitivity_curves.csv", self.curves),
                           ("sensitivity_selection.csv", self.selection),
                           ("sensitivity_facilities.csv", self.facilities),
                           ("sensitivity_municipal.csv", self.municipal),
                           ("sensitivity_network_diagnostics.csv", self.network_summary),
                           ("sensitivity_seed_first_k.csv", self.seed_first)):
            if rows:
                atomic_csv(self.out / name, pd.DataFrame(rows))
        atomic_json(self.out / "progress.json", {"updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                "completed": self.progress,
                                                "selection_rows": len(self.selection)})

    def describe_selected(self, case, method, radius, k, result, chosen_rows, prior_rows, search_runtime):
        labels, centers, runtime, diag, key = result
        df = case.cohort.df
        met, d, nearest, native = evaluate_fit(df, labels, centers, radius, case.metric)
        tag = dict(case=case.name, cohort=case.cohort.name, method=method, radius_km=radius,
                   K_selected=k, seed=42 if method == "K-Means" else -1)
        row = dict(**tag, status="selected", n_candidates=len(case.candidates), metric=case.metric, evaluation_metric=case.metric, fit_metric=adjustment_metric(case, method),
                   fit_space=case.fit_space, center_mode=case.center_mode,
                   estimator=case.cohort.estimator, N_prefixes=len(df),
                   N_unique_buyers=int(case.cohort.orders.customer_unique_id.nunique()),
                   runtime_s=runtime, search_runtime_s=search_runtime,
                   representative_checkpoint=key, candidate_prefixes_sha256=object_sha(df.CEP.iloc[case.candidates].to_list()),
                   **met, **diag)
        for name in ("coverage_pct", "weighted_mean_km", "p95_km", "p99_km", "max_km"):
            row[name + "_seed_min"] = min(r[name] for r in chosen_rows)
            row[name + "_seed_max"] = max(r[name] for r in chosen_rows)
        if prior_rows:
            row["K_minus1_covered_min"] = min(r["covered_orders"] for r in prior_rows)
            row["K_minus1_covered_max"] = max(r["covered_orders"] for r in prior_rows)
            row["K_minus1_margin_min"] = min(r["coverage_margin_orders"] for r in prior_rows)
            row["K_minus1_margin_max"] = max(r["coverage_margin_orders"] for r in prior_rows)
            row["K_minus1_all_seeds_feasible"] = all(r["feasible"] for r in prior_rows)
        row["note"] = case.note or case.cohort.note
        self.selection.append(row)
        facility, segments, geom = geometry_flags(df, centers, nearest, self.union)
        municipalities, muni = municipal_metrics(case.cohort.orders, df, d, radius, self.polygons)
        redistributed = redistribution_metrics(case.cohort.records, df, centers, radius, case.metric)
        for record in facility.to_dict("records"):
            self.facilities.append(dict(**tag, **record))
        for record in municipalities.to_dict("records"):
            self.municipal.append(dict(**tag, **record))
        self.network_summary.append(dict(**tag, **met, **geom, **muni, **redistributed))
        assignment = pd.DataFrame(dict(CEP=df.CEP, n_pedidos=df.n_pedidos,
                                      native_label=labels, nearest_facility=nearest,
                                      distance_km=d, native_distance_km=native,
                                      outside_R=d > radius))
        for key2, value in tag.items():
            assignment[key2] = value
        safe = object_sha(tag)[:20]
        atomic_csv(self.out / "networks" / (safe + "_assignments.csv"), assignment)
        segments = segments[segments.external_union_segment_km_projected > 0].copy()
        for key2, value in tag.items():
            segments[key2] = value
        atomic_csv(self.out / "networks" / (safe + "_external_segments.csv"), segments)

    def run_case(self, case):
        df = case.cohort.df; coords = df[["lat", "lng"]].to_numpy(float)
        D = distances(coords, coords, case.fit_metric or case.metric)
        for method in case.methods:
            print(f"START {case.name} / {method}", flush=True)
            pending = set(RADII); required = required_orders(df.n_pedidos)
            seeds = SEEDS if method == "K-Means" else (-1,)
            max_k = len(case.candidates) if method in DISCRETE else len(df)
            trajectories = {}
            if method in DISCRETE:
                ceiling_d = (D[:, case.candidates].min(axis=1) if (case.fit_metric or case.metric) == case.metric
                             else distances(coords, coords[case.candidates], case.metric).min(axis=1))
                for radius in RADII:
                    ceiling = int(df.n_pedidos.to_numpy()[ceiling_d <= radius].sum())
                    if ceiling < required:
                        self.selection.append(dict(
                            case=case.name, cohort=case.cohort.name, method=method, radius_km=radius,
                            K_selected=None, status="structurally_infeasible",
                            N_orders=int(df.n_pedidos.sum()), N_prefixes=len(df), required_orders=required,
                            n_candidates=len(case.candidates), ceiling_orders=ceiling,
                            ceiling_coverage_pct=100 * ceiling / int(df.n_pedidos.sum()),
                            metric=case.metric, evaluation_metric=case.metric,
                            fit_metric=adjustment_metric(case, method), estimator=case.cohort.estimator, note=case.note))
                        pending.remove(radius)
                if method == "MCLP":
                    for radius in pending:
                        trajectories[radius] = self.store.trajectory(case, D, radius)
            first_seed = {radius: {} for radius in pending}
            seen_by_radius = {radius: [] for radius in pending}
            prior_by_radius = {}; accumulated_runtime = 0
            for k in range(1, max_k + 1):
                if not pending:
                    break
                shared_fits = {}
                if method != "MCLP":
                    for seed in seeds:
                        shared_fits[seed] = fit_at_k(case, method, k, seed, D, self.store)
                    accumulated_runtime += sum(x[2] for x in shared_fits.values())
                for radius in sorted(pending.copy()):
                    fit_rows = []; fits = shared_fits
                    if method == "MCLP":
                        selected, elapsed, key = trajectories[radius]
                        if k > len(selected):
                            self.selection.append(dict(
                                case=case.name, cohort=case.cohort.name, method=method, radius_km=radius,
                                status="greedy_saturated_without_feasibility", K_selected=None,
                                N_orders=int(df.n_pedidos.sum()), required_orders=required,
                                n_candidates=len(case.candidates), note=case.note))
                            pending.remove(radius)
                            continue
                        opened = selected[:k]
                        centers = coords[opened]
                        labels = D[:, opened].argmin(axis=1)
                        fits = {-1: (labels, centers, float(elapsed[k - 1]),
                                     {"trajectory_checkpoint": key}, key)}
                    for seed in seeds:
                        result = fits[seed]
                        met = evaluate_fit(df, result[0], result[1], radius, case.metric)[0]
                        curve = dict(case=case.name, cohort=case.cohort.name, method=method,
                                     radius_km=radius, K=k, seed=seed, runtime_s=result[2],
                                     evaluation_metric=case.metric, fit_metric=adjustment_metric(case, method),
                                     checkpoint=result[4], **met, **result[3])
                        self.curves.append(curve); fit_rows.append(curve)
                        seen_by_radius[radius].append(curve)
                        if met["feasible"] and seed not in first_seed[radius]:
                            first_seed[radius][seed] = k
                    if all(r["feasible"] for r in fit_rows):
                        search_runtime = (float(trajectories[radius][1][-1]) if method == "MCLP"
                                          else accumulated_runtime)
                        self.describe_selected(case, method, radius, k, fits[42 if method == "K-Means" else -1],
                                               fit_rows, prior_by_radius.get(radius, []), search_runtime)
                        for seed in seeds:
                            self.seed_first.append(dict(case=case.name, method=method, radius_km=radius,
                                                        seed=seed, first_feasible_K=first_seed[radius].get(seed),
                                                        simultaneous_first_K=k,
                                                        interpretation="individual first K is not the simultaneous minimum"))
                        pending.remove(radius)
                        print(f"SELECT {case.name} {method} R{radius} K{k}", flush=True)
                    prior_by_radius[radius] = fit_rows
                self.persist()
                if k % 10 == 0:
                    print(f"PROGRESS {case.name} {method} K{k} pending={sorted(pending)}", flush=True)
            for radius in sorted(pending):
                self.selection.append(dict(case=case.name, cohort=case.cohort.name, method=method,
                                           radius_km=radius, status="no_feasible_K_in_complete_domain",
                                           K_selected=None, N_orders=int(df.n_pedidos.sum()),
                                           required_orders=required, domain_max_K=max_k))
            self.progress.append(dict(case=case.name, method=method, completed=True))
            self.persist()

def run_seed_windows(main_case, baseline_selection, store, out):
    rows = []; summaries = []; individual = []
    coords = main_case.cohort.df[["lat", "lng"]].to_numpy(float)
    D = distances(coords, coords); weights = main_case.cohort.df.n_pedidos.to_numpy()
    main_km = baseline_selection[(baseline_selection.case == "main") &
                                 (baseline_selection.method == "K-Means") &
                                 baseline_selection.status.eq("selected")]
    for radius in RADII:
        ksel = int(main_km.loc[main_km.radius_km.eq(radius), "K_selected"].iloc[0])
        low, high = max(1, ksel - 5), ksel + 5
        print(f"SEED WINDOW R{radius}: K{low}..{high}, seeds0..29 plus42", flush=True)
        for k in range(low, high + 1):
            for seed in (*range(30), 42):
                result = fit_at_k(main_case, "K-Means", k, seed, D, store)
                met = evaluate_fit(main_case.cohort.df, result[0], result[1], radius)[0]
                rows.append(dict(radius_km=radius, K=k, seed=seed,
                                 seed_group="sensitivity_30" if seed != 42 else "legacy_representative",
                                 runtime_s=result[2], checkpoint=result[4], **met))
            atomic_csv(Path(out) / "seed30_fits.csv", pd.DataFrame(rows))
        group = pd.DataFrame(rows)
        group = group[(group.radius_km == radius) & group.seed.ne(42)]
        simultaneous = None
        for k, g in group.groupby("K", sort=True):
            if g.feasible.all() and simultaneous is None:
                simultaneous = int(k)
            summaries.append(dict(radius_km=radius, K=int(k), n_seeds=30,
                                  feasible_seeds=int(g.feasible.sum()), feasible_fraction=float(g.feasible.mean()),
                                  coverage_min_pct=float(g.coverage_pct.min()),
                                  coverage_max_pct=float(g.coverage_pct.max()),
                                  p95_min_km=float(g.p95_km.min()), p95_max_km=float(g.p95_km.max()),
                                  p99_min_km=float(g.p99_km.min()), p99_max_km=float(g.p99_km.max()),
                                  max_min_km=float(g.max_km.min()), max_max_km=float(g.max_km.max()),
                                  first_simultaneous_K_within_window=simultaneous))
        for summary in summaries:
            if summary["radius_km"] == radius:
                summary["first_simultaneous_K_within_window"] = simultaneous
        for seed, g in group.groupby("seed", sort=True):
            g = g.sort_values("K")
            viable = g[g.feasible]
            regression = g.feasible.to_numpy()[:-1] & ~g.feasible.to_numpy()[1:]
            individual.append(dict(radius_km=radius, seed=int(seed), window_min_K=low, window_max_K=high,
                                   first_feasible_K_within_window=int(viable.K.iloc[0]) if len(viable) else None,
                                   left_censored=bool(g.iloc[0].feasible),
                                   feasible_to_infeasible_regressions=int(regression.sum()),
                                   first_simultaneous_K_within_window=simultaneous,
                                   interpretation="window sensitivity only; no probability guarantee or global minimal K claim"))
        atomic_csv(Path(out) / "seed30_by_K.csv", pd.DataFrame(summaries))
        atomic_csv(Path(out) / "seed30_by_seed.csv", pd.DataFrame(individual))
    return pd.DataFrame(rows)

def versions_metadata():
    packages = {}
    for name in ("numpy", "pandas", "scikit-learn", "scipy", "shapely", "pyproj"):
        packages[name] = importlib.metadata.version(name)
    return dict(python=platform.python_version(), executable=os.path.realpath(os.sys.executable),
                platform=platform.platform(), packages=packages,
                thread_environment={name: os.environ.get(name) for name in
                                    ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")})
