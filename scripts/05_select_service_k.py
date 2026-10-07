"""Select the first tested integer K meeting order-weighted 95% radius coverage.

This experiment preserves the v21 main configuration. P95/P99 use the empirical
inverse CDF for the decision, with linear percentiles retained as diagnostics.
A K-Means configuration must meet the target at all five specified seeds.
MCLP prefixes reuse one deterministic greedy trajectory per radius; the tie
order and stopping rule are identical to method_mclp_heuristic.
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from candidate_sets import select_candidate_indices

from methods import (
    EARTH_R_KM, haversine_pairwise, haversine_to_centers,
    method_agglomerative, method_pmedian_heuristic,
)

REPO = Path(__file__).resolve().parents[1]
SEEDS = (42, 0, 1, 2, 3)
METHODS = (
    "KMeans-weighted", "Agglomerative-ward", "Agglomerative-complete",
    "Agglomerative-average", "P-Median", "MCLP",
)
TARGET = Fraction(95, 100)
METRIC_INTERVALS = (
    "coverage_pct", "covered_orders", "weighted_avg_distance_km",
    "median_empirical_km",
    "p95_empirical_km", "p99_empirical_km", "p95_linear_km",
    "p99_linear_km", "max_distance_km", "n_facilities", "runtime_s",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer_weights(weights):
    values = np.asarray(weights, dtype=float)
    if (values.ndim != 1 or not np.isfinite(values).all()
            or (values <= 0).any() or (values != np.floor(values)).any()):
        raise ValueError("Demand must contain positive integer order counts")
    if values.sum() > 2**53:
        raise ValueError("Total orders exceed exact float integer arithmetic")
    return values.astype(np.int64)


def required_orders(total_orders, probability=TARGET):
    probability = (probability if isinstance(probability, Fraction)
                   else Fraction(str(probability)))
    if not 0 < probability <= 1 or total_orders <= 0:
        raise ValueError("Positive total and probability in (0, 1] required")
    numerator = int(total_orders) * probability.numerator
    return (numerator + probability.denominator - 1) // probability.denominator


def empirical_quantile(distances, weights, probability):
    """The first observed distance reaching ceil(probability * total orders)."""
    distances = np.asarray(distances, dtype=float)
    counts = integer_weights(weights)
    if (distances.shape != counts.shape or not len(counts)
            or not np.isfinite(distances).all() or (distances < 0).any()):
        raise ValueError("Distances must be finite, nonnegative and match demand")
    order = np.argsort(distances, kind="stable")
    threshold = required_orders(int(counts.sum()), probability)
    position = np.searchsorted(np.cumsum(counts[order]), threshold, side="left")
    return float(distances[order[position]])


def radius_metrics(distances, weights, radius_km):
    distances = np.asarray(distances, dtype=float)
    counts = integer_weights(weights)
    if radius_km <= 0 or not np.isfinite(radius_km):
        raise ValueError("Positive finite radius required")
    p95 = empirical_quantile(distances, counts, TARGET)
    p99 = empirical_quantile(distances, counts, Fraction(99, 100))
    covered = int(counts[distances <= radius_km].sum())
    total = int(counts.sum())
    repeated = np.repeat(distances, counts)
    result = {
        "covered_orders": covered, "outside_orders": total - covered,
        "coverage_pct": 100.0 * covered / total,
        "required_orders": required_orders(total),
        "target_met": bool(covered >= required_orders(total)),
        "p95_empirical_km": p95, "p99_empirical_km": p99,
        "p95_linear_km": float(np.percentile(repeated, 95)),
        "p99_linear_km": float(np.percentile(repeated, 99)),
        "median_empirical_km": empirical_quantile(distances, counts, Fraction(1, 2)),
        "weighted_avg_distance_km": float(np.average(distances, weights=counts)),
        "max_distance_km": float(distances.max()),
    }
    if result["target_met"] != (p95 <= radius_km):
        raise AssertionError("Coverage and empirical P95 decision disagree")
    return result


def all_seeds_feasible(rows, minimum_orders, seeds=SEEDS):
    """Require all specified seeds at the same K, including seeds that regressed."""
    observed = {int(row["seed"]): int(row["covered_orders"]) for row in rows}
    if len(observed) != len(rows):
        raise ValueError("Duplicate seed in one K configuration")
    return all(seed in observed and observed[seed] >= minimum_orders for seed in seeds)


def first_feasible_k(rows, minimum_orders, seeds=None):
    """Audit an exhaustive integer prefix; never binary-search a heuristic curve."""
    grouped = {}
    for row in rows:
        grouped.setdefault(int(row["K_target"]), []).append(row)
    for expected, k in enumerate(sorted(grouped), start=1):
        if k != expected:
            raise ValueError("Every smaller integer K must be evaluated")
        if seeds is None:
            if len(grouped[k]) != 1:
                raise ValueError("Deterministic configurations require one row per K")
            feasible = int(grouped[k][0]["covered_orders"]) >= minimum_orders
        else:
            feasible = all_seeds_feasible(grouped[k], minimum_orders, seeds)
        if feasible:
            return k
    return None


def candidate_coverage_ceiling(distance_matrix, weights, candidates_idx, radius_km):
    """All candidates opened: a structural bound, independent of the heuristic."""
    candidates = np.asarray(candidates_idx, dtype=int)
    if not len(candidates):
        raise ValueError("At least one candidate is required")
    nearest = np.asarray(distance_matrix)[:, candidates].min(axis=1)
    return radius_metrics(nearest, weights, radius_km)


def mclp_greedy_trajectory(distance_matrix, weights, candidates_idx, radius_km):
    """Return global candidate indices and cumulative times for the original greedy.

    Exact integer demand gives the same gains as the original floating sums.
    np.argmax picks the first available maximum, matching its strict > comparison.
    A selected prefix is therefore identical to an independent original fit at K.
    """
    start = time.perf_counter()
    counts = integer_weights(weights)
    candidates = np.asarray(candidates_idx, dtype=int)
    covers = np.asarray(distance_matrix)[:, candidates] <= radius_km
    available = list(range(len(candidates)))
    covered = np.zeros(len(counts), dtype=bool)
    chosen, cumulative = [], []
    while available:
        gains = ((covers[:, available] & ~covered[:, None])
                 * counts[:, None]).sum(axis=0)
        position = int(np.argmax(gains))
        if gains[position] <= 0:
            break
        j = available.pop(position)
        chosen.append(int(candidates[j]))
        covered |= covers[:, j]
        cumulative.append(time.perf_counter() - start)
    return np.asarray(chosen, dtype=int), np.asarray(cumulative, dtype=float)


def atomic_replace_with_retry(temporary, destination):
    """Bounded retry for Windows readers temporarily locking a destination."""
    for delay in (0.05, 0.1, 0.2, 0.4, 0.8, None):
        try:
            temporary.replace(destination)
            return
        except OSError as error:
            windows_lock = getattr(error, "winerror", None) in (32, 33)
            if not isinstance(error, PermissionError) and not windows_lock:
                raise
            if delay is None:
                raise
            time.sleep(delay)


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    atomic_replace_with_retry(temporary, path)


def atomic_csv(path, frame):
    temporary = path.with_name(path.name + ".tmp")
    frame.to_csv(temporary, index=False)
    atomic_replace_with_retry(temporary, path)


class ServiceSearch:
    def __init__(self, demand, input_path, out_dir, radii=(3., 5., 10.),
                 candidates=300, max_k=None, pmedian_max_iter=100):
        self.df = demand.reset_index(drop=True).copy()
        if "CEP" not in self.df:
            self.df = self.df.rename(columns={"customer_zip_code_prefix": "CEP"})
        self.coords = self.df[["lat", "lng"]].to_numpy(dtype=float)
        self.weights = integer_weights(self.df.n_pedidos)
        if (not len(self.df) or not np.isfinite(self.coords).all()
                or self.df.CEP.isna().any() or self.df.CEP.duplicated().any()):
            raise ValueError("Demand needs finite coordinates and unique nonmissing CEPs")
        if (self.coords[:, 0] < -90).any() or (self.coords[:, 0] > 90).any():
            raise ValueError("Latitude out of bounds")
        if (self.coords[:, 1] < -180).any() or (self.coords[:, 1] > 180).any():
            raise ValueError("Longitude out of bounds")
        self.radii = tuple(float(radius) for radius in radii)
        if (not self.radii or len(set(self.radii)) != len(self.radii)
                or any(not np.isfinite(r) or r <= 0 for r in self.radii)):
            raise ValueError("Distinct positive finite radii required")
        if candidates <= 0 or pmedian_max_iter <= 0 or (max_k is not None and max_k <= 0):
            raise ValueError("Candidate, iteration and K limits must be positive")
        self.limit = min(max_k or len(self.df), len(self.df))
        self.pmedian_max_iter = pmedian_max_iter
        self.fit_diagnostics = {}
        self.total = int(self.weights.sum())
        self.minimum = required_orders(self.total)
        self.top = select_candidate_indices(self.df, min(candidates, len(self.df)))
        self.D = haversine_pairwise(self.coords[:, 0], self.coords[:, 1])
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir = self.out / "checkpoints"
        self.checkpoint_dir.mkdir(exist_ok=True)
        versions = {"python": platform.python_version()}
        for package in ("numpy", "pandas", "scikit-learn", "scipy", "shapely", "pyproj"):
            versions[package] = importlib.metadata.version(package)
        source_paths = [Path(__file__).resolve(), REPO / "scripts" / "methods.py",
                        REPO / "scripts" / "candidate_sets.py"]
        protocol = {
            "radii_km": list(self.radii), "target": str(TARGET),
            "seeds": list(SEEDS), "n_init": 10, "max_k": self.limit,
            "kmeans_parameters": {"init": "k-means++", "max_iter": 300, "tol": 1e-4, "algorithm": "lloyd"},
            "candidate_tie_rule": "demand descending, postal prefix ascending",
            "pmedian_max_iter": pmedian_max_iter,
            "candidate_indices": self.top.tolist(), "candidate_count": len(self.top),
            "candidate_CEPs": self.df.loc[self.top, "CEP"].astype(str).tolist(),
            "data_sha256": sha256(input_path),
            "code_sha256": {path.name: sha256(path) for path in source_paths},
            "versions": versions,
        }
        signature = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
        metadata_path = self.out / "service_metadata.json"
        if metadata_path.exists():
            previous = json.loads(metadata_path.read_text(encoding="utf-8"))
            if previous.get("signature") != signature:
                raise ValueError("Checkpoint signature differs; use a new output directory")
        self.metadata = {
            "signature": signature, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol": protocol, "n_demand_points": len(self.df),
            "total_orders": self.total, "required_orders": self.minimum,
            "earth_radius_km": EARTH_R_KM,
            "decision": "covered orders at distance <= R must be >= ceil(0.95*N)",
            "empirical_percentiles": "inverse CDF; first observed distance at ceil(q*N)",
            "linear_percentiles": "numpy.percentile linear over repeated order distances",
            "selection": "first feasible K after testing each smaller integer; no monotonicity assumption",
            "kmeans_rule": "all five seeds meet target at same K; representative seed 42",
            "seed_scope": "five fixed seeds are sensitivity, not a probabilistic guarantee",
            "main_candidates": "demand descending, postal prefix ascending; identical to v21 on the audited prefix-sorted demand CSV",
            "sensitivity": "all demand-point candidates only for structurally infeasible main scenarios",
            "pmedian_termination": "instrumented: no_improving_swap or iteration_limit; passes include final no-improvement pass, swaps count accepted first-improvement exchanges",
            "mclp_runtime": "cumulative greedy trajectory computation through selected prefix; excludes shared distance matrix",
            "mclp_search_runtime": "cumulative[-1] of full greedy trajectory through final chosen candidate, including construction beyond selected K; not a sum of prefix cumulative times; excludes final no-gain check, shared distance matrix, evaluation and exports",
            "other_runtime": "fitting only; p-median uses a shared precomputed distance matrix and an equivalent cached exchange implementation; excludes shared matrix construction, evaluation and exports; hardware dependent",
            "facility_count": "returned centers; unique coordinates and native clusters also reported",
            "evaluation_assignment": "nearest returned facility by Haversine",
            "native_assignment": "original fitted labels retained separately",
            "scope": "exploratory geographic service; no economic/global optimality claim",
            "run_state": "processing",
        }
        curve_path = self.out / "service_curves.csv"
        self.curves = (pd.read_csv(curve_path).to_dict("records")
                       if curve_path.exists() and curve_path.stat().st_size > 1 else [])
        self.curve_keys = {self.row_key(row) for row in self.curves}
        self.selection = {}
        self.selected_fits = {}
        for method in METHODS:
            for radius in self.radii:
                self.initialize_selection("main", method, radius, self.top)
        self.save_snapshot(export_assignments=True)

    @staticmethod
    def row_key(row):
        return (row["scope"], row["method"], float(row["radius_km"]),
                int(row["K_target"]), int(row["seed"]))

    def initialize_selection(self, scope, method, radius, candidates):
        key = (scope, method, radius)
        discrete = method in ("P-Median", "MCLP")
        limit = min(self.limit, len(candidates)) if discrete else self.limit
        self.selection[key] = {
            "scope": scope, "method": method, "radius_km": radius,
            "status": "pending", "K_selected": None, "seed": 42 if method == METHODS[0] else -1,
            "n_demand_points": len(self.df), "total_orders": self.total,
            "required_orders": self.minimum, "search_max_k": limit,
            "last_k_tested": 0, "candidate_count": len(candidates) if discrete else None,
            "target_fraction": float(TARGET),
            "pmedian_max_iter": self.pmedian_max_iter if method == "P-Median" else None,
            "termination_status": ("termination not exposed by legacy function"
                                   if method == "P-Median" else None),
        }
        if discrete:
            ceiling = candidate_coverage_ceiling(self.D, self.weights, candidates, radius)
            self.selection[key].update({
                "candidate_ceiling_pct": ceiling["coverage_pct"],
                "candidate_ceiling_orders": ceiling["covered_orders"],
                "candidate_uncoverable_orders": ceiling["outside_orders"],
            })
            if not ceiling["target_met"]:
                self.selection[key]["status"] = "structurally_infeasible"

    def fit(self, scope, method, k, candidates, seed=-1):
        name = f"{scope}_{method}_K{k}_seed{seed}.npz"
        path = self.checkpoint_dir / name
        if path.exists():
            with np.load(path, allow_pickle=False) as cached:
                self.fit_diagnostics[(scope, method, k, seed)] = (json.loads(str(cached["diagnostics_json"].item()))
                                                               if "diagnostics_json" in cached.files else {})
                return (cached["labels"], cached["centers"],
                        float(cached["runtime_s"].item()))
        diagnostics = {}
        if method == "KMeans-weighted":
            start = time.perf_counter()
            model = KMeans(n_clusters=k, n_init=10, random_state=seed,
                           init="k-means++", max_iter=300, tol=1e-4, algorithm="lloyd")
            labels = model.fit_predict(self.coords, sample_weight=self.weights.astype(float))
            result = labels, model.cluster_centers_, time.perf_counter() - start
        elif method.startswith("Agglomerative-"):
            result = method_agglomerative(self.df, n_clusters=k, linkage=method.split("-")[1])
        elif method == "P-Median":
            augmented = method_pmedian_heuristic(
                self.df, p=k, candidates_idx=candidates, max_iter=self.pmedian_max_iter,
                distance_matrix=self.D, return_diagnostics=True)
            result, diagnostics = augmented[:3], augmented[3]
        else:
            raise ValueError("MCLP requires a radius-specific greedy trajectory")
        temporary = path.with_name(path.name + ".tmp.npz")
        self.fit_diagnostics[(scope, method, k, seed)] = diagnostics
        np.savez_compressed(temporary, labels=result[0], centers=result[1], runtime_s=result[2],
                            diagnostics_json=np.array(json.dumps(diagnostics, sort_keys=True)))
        temporary.replace(path)
        return result

    def record(self, scope, method, radius, k, seed, fitted):
        labels, centers, runtime = fitted
        centers = np.asarray(centers, dtype=float).reshape(-1, 2)
        D = haversine_to_centers(self.coords[:, 0], self.coords[:, 1],
                                 centers[:, 0], centers[:, 1])
        distances = D.min(axis=1)
        row = {
            "scope": scope, "method": method, "radius_km": radius,
            "K_target": int(k), "seed": int(seed), "runtime_s": float(runtime),
            "n_facilities": len(centers),
            "unique_facility_coordinates": len(np.unique(centers, axis=0)),
            "n_native_clusters": len(np.unique(np.asarray(labels)[np.asarray(labels) >= 0])),
            **radius_metrics(distances, self.weights, radius),
        }
        row.update({name: value for name, value in self.fit_diagnostics.get((scope, method, k, seed), {}).items()
                    if name != "pmedian_candidate_indices"})
        key = self.row_key(row)
        if key not in self.curve_keys:
            self.curves.append(row)
            self.curve_keys.add(key)
        self.selection[(scope, method, radius)]["last_k_tested"] = int(k)
        return row

    def select(self, scope, method, radius, k, rows, representative):
        key = (scope, method, radius)
        curve_rows = [row for row in self.curves
                      if (row["scope"], row["method"], float(row["radius_km"])) == key]
        seeds = SEEDS if method == "KMeans-weighted" else None
        if first_feasible_k(curve_rows, self.minimum, seeds=seeds) != k:
            raise AssertionError("Selected K lacks an exhaustive valid prefix")
        reference = next(row for row in rows if int(row["seed"]) == (42 if seeds else -1))
        self.selection[key].update({
            "status": "selected", "K_selected": int(k), **{
                name: reference[name] for name in
                (*METRIC_INTERVALS, "outside_orders", "unique_facility_coordinates",
                 "n_native_clusters")
            },
            "search_runtime_s": (self.selection[key]["search_runtime_s"] if method == "MCLP"
                                 else float(sum(float(row["runtime_s"]) for row in curve_rows))),
        })
        if method == "P-Median":
            self.selection[key].update({name: reference[name] for name in reference if name.startswith("pmedian_")})
            self.selection[key]["termination_status"] = reference.get("pmedian_termination_status", "not_instrumented")
        for name in METRIC_INTERVALS:
            self.selection[key][name + "_min"] = min(row[name] for row in rows)
            self.selection[key][name + "_max"] = max(row[name] for row in rows)
        self.selected_fits[key] = (k, reference["seed"], representative)
        print(f"{scope} {method} R={radius:g} selected K={k}, "
              f"coverage={reference['coverage_pct']:.6f}%", flush=True)
        self.save_snapshot(export_assignments=True)

    def search_non_mclp(self, scope, method, radii, candidates):
        active = [radius for radius in radii
                  if self.selection[(scope, method, radius)]["status"] == "pending"]
        if not active:
            return
        maximum = min(self.limit, len(candidates)) if method == "P-Median" else self.limit
        seeds = SEEDS if method == "KMeans-weighted" else (-1,)
        for k in range(1, maximum + 1):
            group = {radius: [] for radius in active}
            fits = {}
            for seed in seeds:
                fitted = self.fit(scope, method, k, candidates, seed)
                fits[seed] = fitted
                for radius in active:
                    group[radius].append(self.record(scope, method, radius, k, seed, fitted))
                self.save_snapshot()
            for radius in list(active):
                feasible = (all_seeds_feasible(group[radius], self.minimum)
                            if method == "KMeans-weighted"
                            else group[radius][0]["covered_orders"] >= self.minimum)
                if feasible:
                    representative_seed = 42 if method == "KMeans-weighted" else -1
                    self.select(scope, method, radius, k, group[radius], fits[representative_seed])
                    active.remove(radius)
            if not active:
                return
            if k % 10 == 0:
                print(f"{scope} {method} tested all integers through K={k}; "
                      f"pending radii={active}", flush=True)
        for radius in active:
            self.selection[(scope, method, radius)]["status"] = "search_exhausted"
        self.save_snapshot(export_assignments=True)

    def search_mclp(self, scope, radius, candidates):
        key = (scope, "MCLP", radius)
        if self.selection[key]["status"] != "pending":
            return
        path = self.checkpoint_dir / f"{scope}_MCLP_R{radius:g}_trajectory.npz"
        if path.exists():
            with np.load(path, allow_pickle=False) as cached:
                chosen, cumulative = cached["chosen"], cached["cumulative"]
        else:
            chosen, cumulative = mclp_greedy_trajectory(
                self.D, self.weights, candidates, radius)
            temporary = path.with_name(path.name + ".tmp.npz")
            np.savez_compressed(temporary, chosen=chosen, cumulative=cumulative)
            temporary.replace(path)
        self.selection[key]["search_runtime_s"] = (
            float(cumulative[-1]) if len(cumulative) else 0.0)
        maximum = min(self.limit, len(candidates))
        for k in range(1, min(maximum, len(chosen)) + 1):
            selected = chosen[:k]
            centers = self.coords[selected]
            labels = self.D[:, selected].argmin(axis=1)
            fitted = labels, centers, cumulative[k - 1]
            row = self.record(scope, "MCLP", radius, k, -1, fitted)
            self.save_snapshot()
            if row["covered_orders"] >= self.minimum:
                self.select(scope, "MCLP", radius, k, [row], fitted)
                return
        self.selection[key]["status"] = ("greedy_saturated" if len(chosen) <= maximum
                                         else "search_exhausted")
        self.save_snapshot(export_assignments=True)

    def seed_table(self):
        rows = []
        for scope, method, radius in self.selection:
            if method != "KMeans-weighted":
                continue
            for seed in SEEDS:
                tested = [row for row in self.curves
                          if self.row_key(row)[:3] == (scope, method, radius)
                          and int(row["seed"]) == seed]
                hits = [int(row["K_target"]) for row in tested
                        if int(row["covered_orders"]) >= self.minimum]
                rows.append({
                    "scope": scope, "method": method, "radius_km": radius,
                    "seed": seed, "first_feasible_K": min(hits) if hits else None,
                    "last_k_tested": max((int(row["K_target"]) for row in tested), default=0),
                    "status": "target_reached" if hits else "not_reached_in_tested_prefix",
                })
        return pd.DataFrame(rows)

    def export_assignments(self):
        facilities, assignments, tails = [], [], []
        for (scope, method, radius), (k, seed, fitted) in self.selected_fits.items():
            labels, centers, runtime = fitted
            centers = np.asarray(centers).reshape(-1, 2)
            D = haversine_to_centers(self.coords[:, 0], self.coords[:, 1],
                                     centers[:, 0], centers[:, 1])
            nearest = D.argmin(axis=1)
            distances = D[np.arange(len(self.df)), nearest]
            labels = np.asarray(labels, dtype=int)
            native_distances = np.full(len(self.df), np.nan)
            valid = (labels >= 0) & (labels < len(centers))
            native_distances[valid] = D[np.flatnonzero(valid), labels[valid]]
            identifiers = {
                "scope": scope, "method": method, "radius_km": radius,
                "K_selected": k, "seed": int(seed),
            }
            facility = pd.DataFrame({
                **identifiers, "facility_id": np.arange(len(centers)),
                "lat": centers[:, 0], "lng": centers[:, 1],
                "nearest_assigned_orders": np.bincount(
                    nearest, weights=self.weights, minlength=len(centers)).astype(int),
            })
            assignment = self.df.copy()
            for name, value in reversed(list(identifiers.items())):
                assignment.insert(0, name, value)
            assignment["native_label"] = labels
            assignment["nearest_facility"] = nearest
            assignment["distance_km"] = distances
            assignment["native_distance_km"] = native_distances
            assignment["outside_R"] = distances > radius
            # Independent verification from the exact arrays being exported.
            checked = radius_metrics(assignment.distance_km, assignment.n_pedidos, radius)
            selection = self.selection[(scope, method, radius)]
            if checked["covered_orders"] != selection["covered_orders"]:
                raise AssertionError("Exported assignment coverage differs from selected row")
            facilities.append(facility)
            assignments.append(assignment)
            tails.append(assignment[assignment.outside_R].copy())
        for name, frames in (("service_facilities.csv", facilities),
                             ("service_assignments.csv", assignments),
                             ("service_tails.csv", tails)):
            atomic_csv(self.out / name, pd.concat(frames, ignore_index=True)
                       if frames else pd.DataFrame(columns=["scope", "method", "radius_km"]))

    def save_snapshot(self, export_assignments=False):
        frame = pd.DataFrame(self.curves)
        if frame.empty:
            frame = pd.DataFrame(columns=[
                "scope", "method", "radius_km", "K_target", "seed", "covered_orders"])
        atomic_csv(self.out / "service_curves.csv", frame)
        atomic_csv(self.out / "service_selection.csv", pd.DataFrame(self.selection.values()))
        atomic_csv(self.out / "service_seed_first_k.csv", self.seed_table())
        if export_assignments:
            self.export_assignments()
        self.metadata["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        self.metadata["checkpoint_count"] = len(list(self.checkpoint_dir.glob("*.npz")))
        self.metadata["curves_rows"] = len(self.curves)
        self.metadata["selection_rows"] = len(self.selection)
        atomic_json(self.out / "service_metadata.json", self.metadata)

    def run(self):
        for method in METHODS[:-1]:
            self.search_non_mclp("main", method, self.radii, self.top)
        for radius in self.radii:
            self.search_mclp("main", radius, self.top)
        all_candidates = np.arange(len(self.df))
        for method in ("P-Median", "MCLP"):
            for radius in self.radii:
                if self.selection[("main", method, radius)]["status"] == "structurally_infeasible":
                    self.initialize_selection("all_candidates_sensitivity", method, radius, all_candidates)
                    self.save_snapshot(export_assignments=True)
                    if method == "MCLP":
                        self.search_mclp("all_candidates_sensitivity", radius, all_candidates)
                    else:
                        self.search_non_mclp("all_candidates_sensitivity", method, [radius], all_candidates)
        self.metadata["run_state"] = "complete"
        self.save_snapshot(export_assignments=True)
        print(f"Saved {len(self.selection)} scenario selections in {self.out}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO / "data")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--radii", type=float, nargs="+", default=[3, 5, 10])
    parser.add_argument("--candidates", type=int, default=300)
    parser.add_argument("--max-k", type=int)
    parser.add_argument("--pmedian-max-iter", type=int, default=100)
    args = parser.parse_args()
    path = args.data_dir / "demanda_por_cep.csv"
    demand = pd.read_csv(path, dtype={"CEP": str, "customer_zip_code_prefix": str})
    try:
        experiment = ServiceSearch(
            demand, path, args.out_dir or args.data_dir / "service_selection",
            radii=args.radii, candidates=args.candidates, max_k=args.max_k,
            pmedian_max_iter=args.pmedian_max_iter)
        experiment.run()
    except (ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
