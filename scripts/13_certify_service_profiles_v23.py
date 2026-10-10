"""Add finite, count-optimal service alternatives without changing the main pipeline.

The coverage and mandatory-closeness MILP is the same problem evaluated in
v22, here with J825 only. The complete returned primal, selected coordinates,
unrounded profiles and certificates are retained. Mean/P99/municipal profiles
describe ONE count optimum; they are not optimized or unique by this model.
Run 14_verify_service_profiles_v23.py for a separate recalculation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, hstack, identity
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

EARTH_KM = 6371.0088
TARGET_NUMERATOR, TARGET_DENOMINATOR = 95, 100
CASES = [(3., 4.65), (5., 6.60), (10., 12.59),
         (3., None), (3., 15.), (3., 10.), (3., 8.), (3., 6.), (3., 5.),
         (5., None), (5., 15.), (5., 10.), (5., 8.),
         (10., None), (10., 20.), (10., 15.), (10., 13.)]


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False, default=lambda v: v.item() if isinstance(v, np.generic) else str(v)) + "\n", encoding="utf-8")


def distance_matrix(demand, facilities):
    a, b = np.radians(np.asarray(demand, float)), np.radians(np.asarray(facilities, float))
    h = (np.sin((b[None, :, 0]-a[:, None, 0])/2)**2
         + np.cos(a[:, None, 0])*np.cos(b[None, :, 0])
         * np.sin((b[None, :, 1]-a[:, None, 1])/2)**2)
    return 2*EARTH_KM*np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def required(total):
    return (int(total)*TARGET_NUMERATOR+TARGET_DENOMINATOR-1)//TARGET_DENOMINATOR


def empirical(d, w, numerator, denominator):
    order = np.argsort(d, kind="stable")
    rank = (int(w.sum())*numerator+denominator-1)//denominator
    return float(d[order[np.searchsorted(np.cumsum(w[order]), rank)]])


def metrics(d, w, radius):
    covered = int(w[d <= radius].sum())
    return {"K": None, "covered_orders": covered, "outside_orders": int(w.sum())-covered,
            "coverage_pct": 100*covered/int(w.sum()), "target_met": covered >= required(w.sum()),
            "weighted_avg_distance_km": float(np.average(d, weights=w)),
            "median_empirical_km": empirical(d, w, 1, 2),
            "p95_empirical_km": empirical(d, w, 95, 100),
            "p99_empirical_km": empirical(d, w, 99, 100),
            "max_distance_km": float(d.max())}


def municipal_profile(demand, orders, distances, radius, network_id):
    mapping = pd.DataFrame({"customer_zip_code_prefix": demand.customer_zip_code_prefix,
                            "distance_km": distances})
    evaluated = orders[["customer_zip_code_prefix", "city_norm"]].merge(
        mapping, on="customer_zip_code_prefix", how="left", validate="many_to_one")
    if len(evaluated) != int(demand.n_pedidos.sum()) or evaluated.distance_km.isna().any():
        raise ValueError("Municipal profile does not conserve the demand cohort")
    evaluated["covered"] = evaluated.distance_km <= radius
    result = evaluated.groupby("city_norm", sort=True).agg(
        total_orders=("covered", "size"), covered_orders=("covered", "sum")).reset_index()
    result["coverage_pct"] = 100*result.covered_orders/result.total_orders
    result["network_id"] = network_id
    summary = {"municipalities_zero": int((result.covered_orders == 0).sum()),
               "municipalities_below80": int((result.coverage_pct < 80).sum()),
               "orders_in_zero_municipalities": int(result.loc[result.covered_orders == 0, "total_orders"].sum()),
               "orders_in_below80_municipalities": int(result.loc[result.coverage_pct < 80, "total_orders"].sum())}
    return result, summary


def solve_count(distance, weights, radius, maximum, time_limit):
    n, m = distance.shape
    coverage = csr_matrix((distance <= radius).astype(float))
    constraints = [LinearConstraint(hstack([-coverage, identity(n, format="csr")]), -np.inf, 0),
                   LinearConstraint(csr_matrix(np.r_[np.zeros(m), weights][None, :]),
                                    required(weights.sum()), np.inf)]
    if maximum is not None:
        constraints.append(LinearConstraint(hstack([csr_matrix((distance <= maximum).astype(float)),
                                                   csr_matrix((n, n))]), 1, np.inf))
    started = time.perf_counter()
    result = milp(np.r_[np.ones(m), np.zeros(n)],
                  integrality=np.r_[np.ones(m), np.zeros(n)], bounds=Bounds(0, 1),
                  constraints=constraints,
                  options={"time_limit": float(time_limit), "mip_rel_gap": 0., "disp": False})
    certificate = {"status": int(result.status), "success": bool(result.success),
                   "message": str(result.message), "solver": "HiGHS via scipy.optimize.milp",
                   "solver_runtime_s": time.perf_counter()-started,
                   "time_limit_s": float(time_limit), "requested_mip_rel_gap": 0.,
                   "primal_objective": None if result.fun is None else float(result.fun),
                   "dual_bound": None if getattr(result, "mip_dual_bound", None) is None else float(result.mip_dual_bound),
                   "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
                   "mip_node_count": None if getattr(result, "mip_node_count", None) is None else int(result.mip_node_count),
                   "radius_km": float(radius), "mandatory_radius_km": maximum,
                   "required_orders": required(weights.sum()), "total_orders": int(weights.sum()),
                   "n_candidates": m, "n_demand_points": n,
                   "optimality_scope": "Minimum count in finite J825 with weighted partial coverage and optional maximum; no mean/P99/municipal objective",
                   "profile_scope": "Realized profile of one optimum, not a unique or optimized profile"}
    if result.x is None:
        certificate.update(primal_verified=False, solver_certified_optimal=False)
        return certificate, None
    raw_y, raw_z = result.x[:m], result.x[m:]
    chosen = np.flatnonzero(raw_y > .5).astype(np.int64)
    if not len(chosen):
        raise RuntimeError("Solver returned no facilities")
    nearest_index = distance[:, chosen].argmin(axis=1).astype(np.int64)
    d = distance[:, chosen].min(axis=1)
    integrality_error = float(np.abs(raw_y-np.rint(raw_y)).max())
    bounds_error = float(max(0., -result.x.min(), result.x.max()-1.))
    linking_error = float(max(0., (raw_z-coverage@raw_y).max()))
    target_error = float(max(0., required(weights.sum())-weights@raw_z))
    proximity_error = (0. if maximum is None else
                       float(max(0., 1.-((distance <= maximum)@raw_y).min())))
    values = metrics(d, weights, radius)
    values["K"] = len(chosen)
    verified = (integrality_error <= 1e-5 and bounds_error <= 1e-6 and linking_error <= 1e-6
                and target_error <= 1e-5 and proximity_error <= 1e-6 and values["target_met"]
                and (maximum is None or values["max_distance_km"] <= maximum+1e-9)
                and abs(len(chosen)-float(result.fun)) <= 1e-5)
    certificate.update(values)
    certificate.update(max_y_integrality_error=integrality_error, max_bounds_error=bounds_error,
                       max_linking_constraint_error=linking_error, target_constraint_error=target_error,
                       mandatory_constraint_error=proximity_error, primal_verified=bool(verified),
                       solver_certified_optimal=bool(verified and result.status == 0 and result.success
                                                    and certificate["mip_gap"] is not None
                                                    and certificate["mip_gap"] <= 1e-8),
                       integer_bound_matches_K=bool(certificate["dual_bound"] is not None
                                                   and math.ceil(certificate["dual_bound"]-1e-7) == len(chosen)))
    if not verified:
        raise RuntimeError("Returned solver primal fails service-model constraints")
    return certificate, {"primal_y": raw_y, "primal_z": raw_z, "selected_indices": chosen,
                         "nearest_facility": nearest_index, "nearest_distances_km": d}


def name_case(radius, maximum):
    label = "none" if maximum is None else f"{maximum:g}".replace(".", "p")
    return f"J825_R{radius:g}_T{label}"


def comparison_metrics(reference, heuristic, tolerance=1e-9):
    lower = ["K", "weighted_avg_distance_km", "median_empirical_km", "p95_empirical_km",
             "p99_empirical_km", "max_distance_km", "municipalities_zero", "municipalities_below80"]
    flags = {"not_worse_"+c: bool(reference[c] <= heuristic[c]+tolerance) for c in lower}
    flags["not_worse_covered_orders"] = bool(reference["covered_orders"]+tolerance >= heuristic["covered_orders"])
    flags["dominates_K_max"] = bool(flags["not_worse_K"] and flags["not_worse_max_distance_km"]
                                    and (reference["K"] < heuristic["K"]-tolerance
                                         or reference["max_distance_km"] < heuristic["max_distance_km"]-tolerance))
    flags["dominates_K_mean_max"] = bool(flags["dominates_K_max"] and flags["not_worse_weighted_avg_distance_km"])
    flags["dominates_all_recorded_metrics"] = bool(all(flags["not_worse_"+c] for c in lower)
                                                   and flags["not_worse_covered_orders"]
                                                   and any(reference[c] < heuristic[c]-tolerance for c in lower))
    return flags


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--time-limit", type=float, default=600.)
    args = parser.parse_args(argv)
    repo, output = args.repo_root.resolve(), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refusing to overwrite an existing profile experiment")
    output.mkdir(parents=True, exist_ok=True)
    (output/"networks").mkdir()
    sources = {"demand": repo/"data/demanda_por_cep.csv", "orders": repo/"data/pedidos_rmrj_geo.csv",
               "geometry": repo/"data/geography/rj_municipios_ibge.geojson", "scope": repo/"data/geography/scope.json",
               "candidate_sets": repo/"data/v22_verified/exact/candidate_sets.json",
               "main_selection": repo/"data/v22_verified/main/service_selection.csv",
               "main_facilities": repo/"data/v22_verified/main/service_facilities.csv",
               "old_exact_results": repo/"data/v22_verified/exact/exact_results.csv",
               "old_exact_facilities": repo/"data/v22_verified/exact/exact_facilities.csv"}
    manifest = {"schema": "v23_certified_service_profiles_1", "started_utc": datetime.now(timezone.utc).isoformat(),
                "completed": False, "inputs": {k: {"path": str(v), "repo_relative": v.relative_to(repo).as_posix(), "sha256": digest(v)} for k, v in sources.items()},
                "driver_sha256": digest(__file__), "source_commit": "c202b698cead501102efc1024182c7d4f646892d",
                "environment": {"python": sys.version, "numpy": np.__version__, "pandas": pd.__version__,
                                "scipy": scipy.__version__, "shapely": shapely.__version__, "platform": platform.platform(),
                                "thread_environment": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}},
                "configuration": {"target_fraction": "95/100", "earth_radius_km": EARTH_KM,
                                  "municipal_threshold_pct": 80, "count_objective_only": True,
                                  "all_demand_retained": True, "candidate_filter_only": "J825 inside administrative union",
                                  "administrative_union_is_dry_land_mask": False,
                                  "extra_average_thresholds": "T=4.65/6.60/12.59 km, slightly tighter than the reviewed six-decimal thresholds",
                                  "time_limit_s": args.time_limit, "cases": CASES}, "certificates": []}
    write_json(output/"manifest.json", manifest)
    demand, orders = pd.read_csv(sources["demand"]), pd.read_csv(sources["orders"])
    weights = demand.n_pedidos.to_numpy(dtype=np.int64)
    if len(demand) != 828 or int(weights.sum()) != 9691 or len(orders) != 9691:
        raise ValueError("The frozen main cohort differs from 828 prefixes / 9691 orders")
    scope = json.loads(sources["scope"].read_text(encoding="utf-8-sig"))
    geometry = json.loads(sources["geometry"].read_text(encoding="utf-8-sig"))
    union = unary_union([shape(f["geometry"]) for f in geometry["features"]
                         if str(f["properties"]["codarea"]) in set(scope["municipality_codes"])])
    positions = np.asarray(json.loads(sources["candidate_sets"].read_text(encoding="utf-8-sig"))["J825"]["source_positions"], dtype=np.int64)
    candidates = demand.iloc[positions].copy()
    inside = shapely.covers(union, shapely.points(candidates.lng, candidates.lat))
    if len(candidates) != 825 or not np.all(inside) or len(set(positions)) != len(positions):
        raise ValueError("J825 candidate eligibility/order differs")
    candidates.insert(0, "candidate_index", np.arange(len(candidates)))
    candidates.insert(1, "source_position", positions)
    candidates.to_csv(output/"candidates_J825.csv", index=False)
    distances = distance_matrix(demand[["lat", "lng"]], candidates[["lat", "lng"]])
    rows, municipal_rows, facilities_rows = [], [], []
    for radius, maximum in CASES:
        network_id = name_case(radius, maximum)
        print(f"START {network_id}", flush=True)
        certificate, arrays = solve_count(distances, weights, radius, maximum, args.time_limit)
        certificate.update(network_id=network_id, candidate_set="J825", provenance="new v23 solve of the reviewed finite count model")
        if arrays is not None:
            chosen = arrays["selected_indices"]
            selected = candidates.iloc[chosen].copy()
            selected.insert(0, "network_id", network_id)
            selected["facility_id"] = np.arange(len(selected))
            selected["nearest_assigned_orders"] = np.bincount(arrays["nearest_facility"], weights=weights, minlength=len(selected)).astype(np.int64)
            facilities_rows.append(selected)
            mun, summary = municipal_profile(demand, orders, arrays["nearest_distances_km"], radius, network_id)
            certificate.update(summary, selected_outside_union=0, radius_km=radius)
            municipal_rows.append(mun)
            arrays.update(selected_source_positions=positions[chosen], selected_centers=selected[["lat", "lng"]].to_numpy(),
                          weights=weights, demand_coords=demand[["lat", "lng"]].to_numpy(), candidate_coords=candidates[["lat", "lng"]].to_numpy(),
                          candidate_source_positions=positions)
            np.savez_compressed(output/"networks"/(network_id+".npz"), **arrays)
            certificate["npz_sha256"] = digest(output/"networks"/(network_id+".npz"))
        write_json(output/"networks"/(network_id+".json"), certificate)
        manifest["certificates"].append(certificate)
        write_json(output/"manifest.json", manifest)
        rows.append(certificate)
        pd.DataFrame(rows).to_csv(output/"solver_profiles.csv", index=False)
        print(f"DONE {network_id} K={certificate.get('K')} certified={certificate['solver_certified_optimal']} seconds={certificate['solver_runtime_s']:.2f}", flush=True)
    main_selection, main_fac = pd.read_csv(sources["main_selection"]), pd.read_csv(sources["main_facilities"])
    for _, record in main_selection[(main_selection.scope == "main") & main_selection.K_selected.notna()].iterrows():
        selected = main_fac[(main_fac.scope == "main") & (main_fac.method == record.method) & (main_fac.radius_km == record.radius_km)]
        d = distance_matrix(demand[["lat", "lng"]], selected[["lat", "lng"]]).min(axis=1)
        network_id = f"main_{record.method}_R{record.radius_km:g}"
        values = metrics(d, weights, record.radius_km)
        values.update(network_id=network_id, method=record.method, candidate_set="J300" if record.method in ("P-Median", "MCLP") else "continuous_centers_of_partition",
                      radius_km=record.radius_km, K=len(selected), provenance="unchanged frozen v22 main facilities",
                      solver_certified_optimal=False, selected_outside_union=int((~shapely.covers(union, shapely.points(selected.lng, selected.lat))).sum()))
        mun, summary = municipal_profile(demand, orders, d, record.radius_km, network_id)
        values.update(summary)
        rows.append(values)
        municipal_rows.append(mun)
    old_results, old_fac = pd.read_csv(sources["old_exact_results"]), pd.read_csv(sources["old_exact_facilities"])
    for old_id in ("maximal_J300_R5_K39", "maximal_J300_R10_K14", "partial_J825_grid500_R3", "partial_J825_grid500_R5", "partial_J825_grid500_R10"):
        record = old_results.loc[old_results.job_id == old_id].iloc[0]
        selected = old_fac.loc[old_fac.job_id == old_id]
        d = distance_matrix(demand[["lat", "lng"]], selected[["lat", "lng"]]).min(axis=1)
        values = metrics(d, weights, record.radius_km)
        for key in ("weighted_avg_distance_km", "p99_empirical_km", "max_distance_km", "covered_orders"):
            if not np.isclose(values[key], record[key], rtol=1e-10, atol=1e-9):
                raise ValueError(f"Frozen {old_id} {key} mismatch")
        values.update(network_id=old_id, candidate_set=record.candidate_set, radius_km=record.radius_km, K=len(selected),
                      solver_certified_optimal=bool(record.solver_certified_optimal), provenance="unchanged exported v22 exact facilities, primal re-evaluated",
                      selected_outside_union=int((~shapely.covers(union, shapely.points(selected.lng, selected.lat))).sum()))
        mun, summary = municipal_profile(demand, orders, d, record.radius_km, old_id)
        values.update(summary)
        rows.append(values)
        municipal_rows.append(mun)
    table = pd.DataFrame(rows)
    table.to_csv(output/"all_network_profiles.csv", index=False)
    pd.concat(municipal_rows, ignore_index=True).to_csv(output/"municipal_profiles.csv", index=False)
    pd.concat(facilities_rows, ignore_index=True).to_csv(output/"selected_facilities.csv", index=False)
    comparisons = []
    for _, reference in table[(table.network_id.str.startswith("J825_R")) | table.network_id.str.startswith("maximal_J300")].iterrows():
        if not reference.solver_certified_optimal:
            continue
        for _, heuristic in table[table.network_id.str.startswith("main_") & (table.radius_km == reference.radius_km)].iterrows():
            row = {"reference_id": reference.network_id, "heuristic_id": heuristic.network_id, "radius_km": reference.radius_km,
                   "comparison_scope": "same cohort/metric/service target; candidate spaces may differ",
                   "same_J300": bool(reference.candidate_set == "J300" and heuristic.candidate_set == "J300")}
            for key in ("K", "covered_orders", "weighted_avg_distance_km", "p99_empirical_km", "max_distance_km", "municipalities_zero", "municipalities_below80"):
                row["reference_"+key], row["heuristic_"+key] = reference[key], heuristic[key]
            row.update(comparison_metrics(reference, heuristic))
            comparisons.append(row)
    pd.DataFrame(comparisons).to_csv(output/"profile_comparisons.csv", index=False)
    lower_bounds = []
    for _, heuristic in table[table.network_id.str.startswith("main_")].iterrows():
        grid = table.loc[table.network_id == f"partial_J825_grid500_R{heuristic.radius_km:g}"].iloc[0]
        lower_bounds.append({"network_id": heuristic.network_id, "radius_km": heuristic.radius_km, "K_heuristic": heuristic.K,
                             "grid_feasible_K": grid.K, "count_excess_lower_bound": heuristic.K-grid.K,
                             "heuristic_admissible_in_union": heuristic.selected_outside_union == 0,
                             "scope": "continuous count minimum in administrative union for coverage95 only; no maximum/mean/municipal constraints; not a gap of clustering objectives"})
    pd.DataFrame(lower_bounds).to_csv(output/"count_lower_bounds.csv", index=False)
    numeric_values, numeric_sources = {}, {}
    for prefix, frame, path, key in (
            ("profile", table, output/"all_network_profiles.csv", "network_id"),
            ("profile_lower_bound", pd.DataFrame(lower_bounds), output/"count_lower_bounds.csv", "network_id")):
        numeric_sources[str(path)] = digest(path)
        for _, value_row in frame.iterrows():
            for column in frame.select_dtypes(include="number").columns:
                value = value_row[column]
                if pd.isna(value):
                    continue
                numeric_values[f"{prefix}.{value_row[key]}.{column}"] = {
                    "value": value, "file": str(path), "column": column,
                    "filter": {key: value_row[key]}, "aggregation": "identity",
                    "category": "operational_observation" if column == "solver_runtime_s" else
                                ("protocol" if column in ("radius_km", "mandatory_radius_km", "time_limit_s") else "scientific_result")}
    write_json(output/"paper_numeric_catalog_profiles_v23.json", {"values": numeric_values, "source_hashes": numeric_sources})
    write_json(output/"paper_values_profiles_v23.json", {"schema": "v23_profile_values_1", "networks": table.astype(object).where(pd.notna(table), None).to_dict("records"),
                                                       "comparisons": comparisons, "count_lower_bounds": lower_bounds,
                                                       "rounding_policy": "full precision here; presentation rounding is separate",
                                                       "interpretation": "dominance axes are explicit; no universal/Pareto-frontier/physical-network optimality claim"})
    output.joinpath("LEIA_ME.txt").write_text(
        "Extensão isolada da v23. A condição principal da v22 não foi recalculada nem substituída.\n"
        "São 17 modelos de menor quantidade em J825, com cobertura ponderada >=95% e proximidade obrigatória opcional.\n"
        "T=4,65/6,60/12,59 km é ligeiramente mais estrito que o limiar Average do parecer.\n"
        "Média, P99 e atendimento municipal descrevem um ótimo de quantidade; não são objetivos otimizados.\n"
        "K/max é uma comparação de dois eixos, não dominância em todos os indicadores.\n"
        "J825 e grades são elegíveis na união administrativa, sem certificação de terra seca, comércio ou acessibilidade.\n"
        "O limite inferior K_heur-K_grade usa só cobertura95%, não conserva média/máximo/municípios.\n"
        "O verificador 14 recalcula métricas e primal sem importar o solver 13 ou os módulos científicos da v22.\n"
        "As certificações de otimalidade são do HiGHS; não há segundo solver. Tempos são observações operacionais.\n", encoding="utf-8")
    manifest.update(completed=True, completed_utc=datetime.now(timezone.utc).isoformat(),
                    all_17_solver_certified=all(x["solver_certified_optimal"] for x in manifest["certificates"]),
                    output_hashes={str(p.relative_to(output)).replace("\\", "/"): digest(p)
                                   for p in sorted(output.rglob("*")) if p.is_file() and p.name != "manifest.json"})
    write_json(output/"manifest.json", manifest)
    print(f"COMPLETE networks={len(table)} new_cases={len(CASES)} all_certified={manifest['all_17_solver_certified']}", flush=True)
    return 0 if manifest["all_17_solver_certified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
