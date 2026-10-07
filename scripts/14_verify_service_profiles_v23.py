"""Independent recalculation of v23 profiles, coordinates and solver primals.

No import of driver 13 or any model/metric module of the repository. This checks
finite model feasibility and the recorded HiGHS count bound, not a second-solver
certificate and not global optimization of distance or territorial indicators.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union


def file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def distances_to_centres(prefixes, centres):
    """Separate arctan2 Haversine implementation with unrounded coordinates."""
    lat1, lon1 = np.deg2rad(np.asarray(prefixes).T)
    lat2, lon2 = np.deg2rad(np.asarray(centres).T)
    dlat = lat2[None, :]-lat1[:, None]
    dlon = lon2[None, :]-lon1[:, None]
    chord = np.sin(dlat/2)**2 + np.cos(lat1[:, None])*np.cos(lat2[None, :])*np.sin(dlon/2)**2
    chord = np.clip(chord, 0., 1.)
    return 2*6371.0088*np.arctan2(np.sqrt(chord), np.sqrt(1-chord))


def weighted_rank(distance, counts, numerator, denominator):
    ordered_pairs = sorted(zip(distance.tolist(), counts.tolist()), key=lambda x: x[0])
    target_rank = (sum(int(c) for c in counts)*numerator+denominator-1)//denominator
    accumulator = 0
    for value, count in ordered_pairs:
        accumulator += int(count)
        if accumulator >= target_rank:
            return float(value)
    raise ValueError("Weighted empirical rank could not be reached")


def recompute_profile(d, w, radius, k):
    total = sum(int(c) for c in w)
    covered = sum(int(count) for count, distance in zip(w, d) if distance <= radius)
    return {"K": int(k), "covered_orders": covered, "outside_orders": total-covered,
            "coverage_pct": 100*covered/total,
            "weighted_avg_distance_km": sum(float(a)*int(b) for a, b in zip(d, w))/total,
            "median_empirical_km": weighted_rank(d, w, 1, 2),
            "p95_empirical_km": weighted_rank(d, w, 95, 100),
            "p99_empirical_km": weighted_rank(d, w, 99, 100), "max_distance_km": float(max(d))}


def calculate_municipal(demand, orders, d, radius):
    prefix_distances = dict(zip(demand.customer_zip_code_prefix.astype(int), d))
    summary = {}
    for prefix, city in orders[["customer_zip_code_prefix", "city_norm"]].itertuples(index=False, name=None):
        total, covered = summary.get(city, (0, 0))
        summary[city] = (total+1, covered+int(prefix_distances[int(prefix)] <= radius))
    table = [{"city_norm": city, "total_orders": total, "covered_orders": covered,
              "coverage_pct": 100*covered/total} for city, (total, covered) in sorted(summary.items())]
    return table, {"municipalities_zero": sum(v[1] == 0 for v in summary.values()),
                   "municipalities_below80": sum(v[1]/v[0] < .8 for v in summary.values()),
                   "orders_in_zero_municipalities": sum(v[0] for v in summary.values() if v[1] == 0),
                   "orders_in_below80_municipalities": sum(v[0] for v in summary.values() if v[1]/v[0] < .8)}


def primal_checks(D, w, y, z, selected, radius, maximum, certificate):
    """Check every linking, target, bound and optional proximity constraint."""
    target = (sum(int(v) for v in w)*95+99)//100
    m = D.shape[1]
    checks = {"vector_dimensions": y.shape == (m,) and z.shape == (len(w),),
              "finite_vectors": bool(np.isfinite(y).all() and np.isfinite(z).all()),
              "binary_facilities": bool(np.max(np.abs(y-np.rint(y))) <= 1e-5),
              "bounds_y": bool(np.min(y) >= -1e-6 and np.max(y) <= 1+1e-6),
              "bounds_z": bool(np.min(z) >= -1e-6 and np.max(z) <= 1+1e-6),
              "selected_matches_primal": bool(np.array_equal(np.flatnonzero(y > .5), selected)),
              "covered_linking_constraints": bool(np.max(z-(D <= radius)@y) <= 1e-6),
              "weighted_target_constraint": bool(w@z >= target-1e-5),
              "mandatory_linking_constraints": maximum is None or bool(np.min((D <= maximum)@y) >= 1-1e-6),
              "objective_from_primal": abs(float(y.sum())-certificate["primal_objective"]) <= 1e-5,
              "integer_objective_from_selection": abs(len(selected)-certificate["primal_objective"]) <= 1e-5,
              "recorded_optimal_status": certificate["status"] == 0 and certificate["success"] is True,
              "recorded_gap": certificate["mip_gap"] is not None and certificate["mip_gap"] <= 1e-8,
              "recorded_bound_matches_count": certificate["dual_bound"] is not None and math.ceil(certificate["dual_bound"]-1e-7) == len(selected)}
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    directory = args.profiles.resolve()
    report_path = args.report or directory/"independent_verification.json"
    manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    checks, failures, network_checks = [], [], []

    def check(name, ok, detail=None):
        entry = {"check": name, "passed": bool(ok)}
        if detail is not None:
            entry["detail"] = detail
        checks.append(entry)
        if not ok:
            failures.append(entry)

    check("manifest_complete", manifest["completed"] is True)
    check("17_cases_certified", manifest["all_17_solver_certified"] is True and len(manifest["certificates"]) == 17)
    sources = {}
    for name, entry in manifest["inputs"].items():
        path = args.repo_root/entry["repo_relative"] if args.repo_root else Path(entry["path"])
        sources[name] = path
        check("source_hash:"+name, file_hash(path) == entry["sha256"])
    for relative, expected in manifest["output_hashes"].items():
        check("output_hash:"+relative, file_hash(directory/relative) == expected)
    demand, orders = pd.read_csv(sources["demand"]), pd.read_csv(sources["orders"])
    w = demand.n_pedidos.to_numpy(dtype=np.int64)
    coords = demand[["lat", "lng"]].to_numpy()
    positions = np.asarray(json.loads(sources["candidate_sets"].read_text(encoding="utf-8-sig"))["J825"]["source_positions"], dtype=np.int64)
    candidate_coords = coords[positions]
    D = distances_to_centres(coords, candidate_coords)
    scope = json.loads(sources["scope"].read_text(encoding="utf-8-sig"))
    geojson = json.loads(sources["geometry"].read_text(encoding="utf-8-sig"))
    region = unary_union([shape(f["geometry"]) for f in geojson["features"] if str(f["properties"]["codarea"]) in scope["municipality_codes"]])
    check("J825_unique_positions", len(positions) == 825 and len(set(positions)) == 825)
    check("J825_inside_union", np.all(shapely.covers(region, shapely.points(candidate_coords[:, 1], candidate_coords[:, 0]))))
    table = pd.read_csv(directory/"all_network_profiles.csv")
    municipal = pd.read_csv(directory/"municipal_profiles.csv")
    recomputed_rows = []
    facilities = pd.read_csv(sources["main_facilities"])
    old_facilities = pd.read_csv(sources["old_exact_facilities"])
    for _, row in table.iterrows():
        network_id = row.network_id
        if network_id.startswith("J825_R"):
            certificate = json.loads((directory/"networks"/(network_id+".json")).read_text(encoding="utf-8"))
            arrays = np.load(directory/"networks"/(network_id+".npz"), allow_pickle=False)
            selected = arrays["selected_indices"]
            network_centres = candidate_coords[selected]
            check(network_id+":saved_centres_match", np.array_equal(network_centres, arrays["selected_centers"]))
            check(network_id+":saved_positions_match", np.array_equal(positions[selected], arrays["selected_source_positions"]))
            check(network_id+":demand_matches", np.array_equal(coords, arrays["demand_coords"]) and np.array_equal(w, arrays["weights"]))
            check(network_id+":candidate_array_matches", np.array_equal(candidate_coords, arrays["candidate_coords"]) and np.array_equal(positions, arrays["candidate_source_positions"]))
            for label, ok in primal_checks(D, w, arrays["primal_y"], arrays["primal_z"], selected,
                                           row.radius_km, certificate["mandatory_radius_km"], certificate).items():
                check(network_id+":"+label, ok)
            d = distances_to_centres(coords, network_centres).min(axis=1)
            check(network_id+":saved_distances_match", np.allclose(d, arrays["nearest_distances_km"], rtol=1e-11, atol=1e-9))
            nearest_distances = distances_to_centres(coords, network_centres)
            check(network_id+":assignment_is_nearest", np.allclose(nearest_distances[np.arange(len(w)), arrays["nearest_facility"]], d, rtol=1e-11, atol=1e-9))
            check(network_id+":mandatory_realized", certificate["mandatory_radius_km"] is None or d.max() <= certificate["mandatory_radius_km"]+1e-9)
            arrays.close()
        elif network_id.startswith("main_"):
            f = facilities[(facilities.scope == "main") & (facilities.method == row.method) & (facilities.radius_km == row.radius_km)]
            network_centres = f[["lat", "lng"]].to_numpy()
            d = distances_to_centres(coords, network_centres).min(axis=1)
        else:
            f = old_facilities[old_facilities.job_id == network_id]
            network_centres = f[["lat", "lng"]].to_numpy()
            d = distances_to_centres(coords, network_centres).min(axis=1)
        profile = recompute_profile(d, w, row.radius_km, len(network_centres))
        mun, summary = calculate_municipal(demand, orders, d, row.radius_km)
        profile.update(summary, selected_outside_union=int((~shapely.covers(region, shapely.points(network_centres[:, 1], network_centres[:, 0]))).sum()))
        for label, value in profile.items():
            check(network_id+":metric:"+label, np.isclose(value, row[label], rtol=1e-10, atol=1e-8))
        expected_municipal = municipal[municipal.network_id == network_id].sort_values("city_norm")
        for record, (_, expected_row) in zip(mun, expected_municipal.iterrows()):
            check(network_id+":municipal:"+record["city_norm"], record["city_norm"] == expected_row.city_norm
                  and record["total_orders"] == expected_row.total_orders and record["covered_orders"] == expected_row.covered_orders
                  and np.isclose(record["coverage_pct"], expected_row.coverage_pct, atol=1e-9))
        check(network_id+":municipal_row_count", len(mun) == len(expected_municipal))
        check(network_id+":target_met", profile["covered_orders"] >= (int(w.sum())*95+99)//100)
        profile.update(network_id=network_id, radius_km=row.radius_km)
        recomputed_rows.append(profile)
        network_checks.append({"network_id": network_id, "metrics_recomputed": True})
    computed = pd.DataFrame(recomputed_rows).set_index("network_id")
    pairs = pd.read_csv(directory/"profile_comparisons.csv")
    lower_axes = ["K", "weighted_avg_distance_km", "median_empirical_km", "p95_empirical_km",
                  "p99_empirical_km", "max_distance_km", "municipalities_zero", "municipalities_below80"]
    for i, pair in pairs.iterrows():
        a, b = computed.loc[pair.reference_id], computed.loc[pair.heuristic_id]
        flags = {key: a[key] <= b[key]+1e-9 for key in lower_axes}
        cover_flag = a.covered_orders+1e-9 >= b.covered_orders
        two_axes = flags["K"] and flags["max_distance_km"] and (a.K < b.K-1e-9 or a.max_distance_km < b.max_distance_km-1e-9)
        check(f"comparison:{i}:K_max", bool(two_axes) == bool(pair.dominates_K_max))
        check(f"comparison:{i}:K_mean_max", bool(two_axes and flags["weighted_avg_distance_km"]) == bool(pair.dominates_K_mean_max))
        check(f"comparison:{i}:all_recorded", bool(all(flags.values()) and cover_flag and any(a[k] < b[k]-1e-9 for k in lower_axes)) == bool(pair.dominates_all_recorded_metrics))
    for _, lower in pd.read_csv(directory/"count_lower_bounds.csv").iterrows():
        grid = computed.loc[f"partial_J825_grid500_R{lower.radius_km:g}"]
        heuristic = computed.loc[lower.network_id]
        check(lower.network_id+":continuous_count_bound", grid.selected_outside_union == 0 and grid.covered_orders >= (int(w.sum())*95+99)//100
              and lower.count_excess_lower_bound == heuristic.K-grid.K
              and bool(lower.heuristic_admissible_in_union) == bool(heuristic.selected_outside_union == 0))
    report = {"schema": "v23_profiles_independent_check_1", "completed_utc": datetime.now(timezone.utc).isoformat(),
              "verifier_sha256": file_hash(__file__), "manifest_sha256": file_hash(directory/"manifest.json"),
              "passed": not failures, "network_count": len(network_checks), "check_count": len(checks),
              "failure_count": len(failures), "failures": failures, "checks": checks,
              "scope": "Independent primal/metric/table/municipal comparison recalculation; reads the recorded HiGHS status and dual bound; no second solver or mean/Pareto optimality certification"}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("passed", "network_count", "check_count", "failure_count")}, ensure_ascii=False))
    if failures:
        print(json.dumps(failures[:10], ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
