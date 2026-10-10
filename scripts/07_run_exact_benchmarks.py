"""Run the approved finite exact references in an isolated output folder."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time
import numpy as np
import pandas as pd
from candidate_sets import (grid_candidates, inside_union_mask, load_municipal_union,
                            normalized_prefixes, postal_candidates, select_candidate_indices)
from exact_benchmarks import (haversine_distance_matrix, required_orders, solve_maximal_cover,
                              solve_partial_cover, solve_pmedian, validated_weights)

REPO = Path(__file__).resolve().parents[1]
TAIL_SCENARIOS = {3: (None, 15, 10, 8, 5), 5: (None, 15, 10, 8), 10: (None, 30, 20, 15)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def run(args):
    data, out = args.data_dir.resolve(), args.out_dir.resolve()
    if out == data or (out.exists() and any(out.iterdir())):
        raise ValueError("Use an empty, isolated output directory")
    paths = {
        "demand": data/"demanda_por_cep.csv", "orders": data/"pedidos_rmrj_geo.csv",
        "geometry": data/"geography/rj_municipios_ibge.geojson", "scope": data/"geography/scope.json",
        "reference_metadata": args.reference_dir/"service_metadata.json",
        "reference_selection": args.reference_dir/"service_selection.csv",
        "reference_curves": args.reference_dir/"service_curves.csv",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    input_hashes = {name: sha(path) for name, path in paths.items()}
    demand = pd.read_csv(paths["demand"], dtype={"CEP": str, "customer_zip_code_prefix": str}).reset_index(drop=True)
    weights = validated_weights(demand.n_pedidos)
    total, target = int(weights.sum()), required_orders(int(weights.sum()))
    if len(demand) != 828 or total != 9691:
        raise ValueError("This protocol requires the preserved 828-prefix / 9691-order principal cohort")
    coords = demand[["lat", "lng"]].to_numpy(dtype=float)
    prefixes = normalized_prefixes(demand)
    orders = pd.read_csv(paths["orders"], dtype={"customer_zip_code_prefix": str})
    if len(orders) != total or orders.order_id.duplicated().any() or orders.city_norm.isna().any():
        raise ValueError("Principal order keys/counts/cities are inconsistent")
    order_positions = pd.Index(prefixes).get_indexer(normalized_prefixes(orders))
    if (order_positions < 0).any() or not np.array_equal(
            np.bincount(order_positions, minlength=len(weights)), weights):
        raise ValueError("Order-level municipal denominators must match the complete demand")
    union = load_municipal_union(paths["geometry"], paths["scope"])
    eligible = inside_union_mask(coords, union)
    principal = select_candidate_indices(demand, 300)
    reverse = select_candidate_indices(demand, 300, tie_order="descending")
    old_metadata = json.loads(paths["reference_metadata"].read_text(encoding="utf-8"))
    if input_hashes["demand"] != old_metadata["protocol"]["data_sha256"]:
        raise ValueError("Demand differs from the frozen v21 principal cohort")
    if int(eligible.sum()) != 825:
        raise ValueError("This geometry must leave the audited 825 eligible postal candidates")
    if not np.array_equal(principal, old_metadata["protocol"]["candidate_indices"]):
        raise ValueError("Canonical J300 order differs from the v21 reference")
    out.mkdir(parents=True, exist_ok=True)
    code_paths = [Path(__file__).resolve(), REPO/"scripts/exact_benchmarks.py", REPO/"scripts/candidate_sets.py"]
    metadata = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "versions": {"python": platform.python_version(), **{
            p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scipy", "shapely", "pyproj")}},
        "platform": platform.platform(), "total_orders": total, "n_prefixes": len(demand),
        "required_orders": target, "input_sha256": input_hashes,
        "code_sha256": {p.name: sha(p) for p in code_paths},
        "solver": "embedded HiGHS via scipy.optimize.milp",
        "solver_options": {"time_limit_s": args.time_limit, "mip_rel_gap": 0.0},
        "assignment": "nearest selected facility by Haversine; first minimum resolves distance ties",
        "municipality": "city_norm declared per delivered order; no inferred municipality in principal",
        "candidate_scope": "finite candidate sets; municipal union is an administrative proxy",
        "interpretation": "no continuous/economic optimum; metrics describe a particular returned optimum",
        "principal_condition": "v21 canonical J300 and degree-based clustering preserved elsewhere",
        "runtime_scope": "solver_runtime_s excludes setup, distance matrix and export; total run is separate",
        "tail_scenarios": {str(k): list(v) for k, v in TAIL_SCENARIOS.items()},
        "run_state": "processing",
        "volatile_fields": ["solver_runtime_s", "setup_runtime_s", "started_at_utc", "finished_at_utc", "total_runtime_s"],
    }
    json_write(out/"exact_metadata.json", metadata)
    selections = pd.read_csv(paths["reference_selection"])
    curves = pd.read_csv(paths["reference_curves"])
    rows, facilities, assignments, municipalities = [], [], [], []
    set_metadata, candidate_cache, distance_cache = {}, {}, {}
    pmedian_comparisons = []
    started_all = time.perf_counter()

    def register(name, frame, extra=None, cache=False):
        frame = frame.reset_index(drop=True)
        coord_array = frame[["lat", "lng"]].to_numpy(dtype="<f8")
        description = {
            "candidate_count": len(frame), "outside_union": int((~frame.inside_union).sum()),
            "ordered_ids_sha256": hashlib.sha256(json.dumps(frame.candidate_id.tolist()).encode()).hexdigest(),
            "coordinates_sha256": hashlib.sha256(coord_array.tobytes()).hexdigest(),
            "source_kinds": frame.source_kind.value_counts().to_dict(),
            "eligibility": "postal facilities optionally filtered; all demand/orders retained",
            **(extra or {}),
        }
        if frame.source_kind.eq("postal_mean").all():
            description["source_positions"] = frame.source_position.astype(int).tolist()
        set_metadata[name] = description
        if cache:
            candidate_cache[name] = frame
            distance_cache[name] = haversine_distance_matrix(coords, coord_array)
        return frame

    def export(job, name, frame, distances, solution):
        row = {
            "job_id": job, "candidate_set": name, "analysis_scope": "finite_exact_reference",
            "candidate_outside_union": int((~frame.inside_union).sum()),
            "demand_sha256": input_hashes["demand"], **solution.certificate,
        }
        row["K"] = row["n_facilities"] if row["has_primal_solution"] else None
        if row["has_primal_solution"]:
            chosen = frame.iloc[solution.selected_indices].copy().reset_index(drop=True)
            chosen.insert(0, "facility_id", np.arange(len(chosen)))
            chosen.insert(0, "candidate_set", name)
            chosen.insert(0, "job_id", job)
            row["selected_outside_union"] = int((~chosen.inside_union).sum())
            chosen["nearest_assigned_orders"] = np.bincount(
                solution.nearest_facility, weights=weights, minlength=len(chosen)).astype(int)
            facilities.append(chosen)
            assigned = pd.DataFrame({
                "job_id": job, "candidate_set": name, "postal_prefix": prefixes,
                "lat": coords[:, 0], "lng": coords[:, 1], "n_pedidos": weights,
                "nearest_facility": solution.nearest_facility,
                "distance_km": solution.nearest_distances_km,
                "inside_R": solution.nearest_distances_km <= row["radius_km"],
            })
            assignments.append(assigned)
            od = solution.nearest_distances_km[order_positions]
            municipal = orders.assign(distance_km=od, covered=od <= row["radius_km"]).groupby(
                "city_norm", sort=True).agg(total_orders=("covered", "size"),
                    covered_orders=("covered", "sum"),
                    mean_distance_km=("distance_km", "mean"),
                    max_distance_km=("distance_km", "max")).reset_index()
            municipal["outside_orders"] = municipal.total_orders-municipal.covered_orders
            municipal["coverage_pct"] = 100*municipal.covered_orders/municipal.total_orders
            municipal.insert(0, "candidate_set", name)
            municipal.insert(0, "job_id", job)
            assert int(municipal.total_orders.sum()) == total
            assert int(municipal.covered_orders.sum()) == row["covered_orders"]
            municipalities.append(municipal)
            zero, below = municipal.coverage_pct.eq(0), municipal.coverage_pct.lt(80)
            row.update({
                "municipalities_zero": int(zero.sum()),
                "orders_in_zero_municipalities": int(municipal.loc[zero, "total_orders"].sum()),
                "municipalities_below80": int(below.sum()),
                "orders_in_below80_municipalities": int(municipal.loc[below, "total_orders"].sum()),
                "Rio_outside_orders": int(((orders.city_norm.eq("rio de janeiro")) & (od > row["radius_km"])).sum()),
            })
            row["Rio_share_of_outside_pct"] = (
                100*row["Rio_outside_orders"]/row["outside_orders"] if row["outside_orders"] else None)
        else:
            row["selected_outside_union"] = None
        rows.append(row)
        json_write(out/"exact_results.json", rows)
        pd.DataFrame(rows).to_csv(out/"exact_results.csv", index=False)
        json_write(out/"candidate_sets.json", set_metadata)
        print(f"{job}: status={row['status']}, K={row['K']}, gap={row['mip_gap']}, "
              f"covered={row.get('covered_orders')}", flush=True)
        return row

    for name, indices in (
            ("J300", principal), ("J300_reverse", reverse),
            ("J828", np.arange(len(demand))), ("J825", np.flatnonzero(eligible))):
        frame = register(name, postal_candidates(demand, indices, union), cache=True)
        for radius in (3, 5, 10):
            result = solve_partial_cover(distance_cache[name], weights, radius, time_limit=args.time_limit)
            export(f"partial_{name}_R{radius}", name, frame, distance_cache[name], result)

    for step in (1000, 500):
        for filtered in (False, True):
            name = f"J{'825' if filtered else '828'}_grid{step}"
            frame, description = grid_candidates(demand, union, step, filter_postal=filtered)
            register(name, frame, description)
            distances = haversine_distance_matrix(coords, frame[["lat", "lng"]].to_numpy())
            for radius in (3, 5, 10):
                result = solve_partial_cover(distances, weights, radius, time_limit=args.time_limit)
                export(f"partial_{name}_R{radius}", name, frame, distances, result)
            del distances

    for name, scope, radius in (("J300", "main", 5), ("J300", "main", 10),
                                ("J828", "all_candidates_sensitivity", 3)):
        selected = selections[(selections.scope == scope) & (selections.method == "MCLP")
                              & (selections.radius_km == radius)]
        if len(selected) != 1 or selected.status.iloc[0] != "selected":
            raise ValueError("Missing selected greedy MCLP reference")
        budget = int(selected.K_selected.iloc[0])-1
        result = solve_maximal_cover(distance_cache[name], weights, budget, radius, time_limit=args.time_limit)
        row = export(f"maximal_{name}_R{radius}_K{budget}", name, candidate_cache[name], distance_cache[name], result)
        row["greedy_selected_K_reference"] = budget+1
    result = solve_maximal_cover(distance_cache["J825"], weights, 300, 3, time_limit=args.time_limit)
    export("existence_J825_R3_K300", "J825", candidate_cache["J825"], distance_cache["J825"], result)

    for radius, limits in TAIL_SCENARIOS.items():
        for maximum in limits:
            result = solve_partial_cover(distance_cache["J828"], weights, radius,
                        mandatory_radius_km=maximum, time_limit=args.time_limit)
            suffix = "none" if maximum is None else str(maximum)
            export(f"proximity_J828_R{radius}_T{suffix}", "J828", candidate_cache["J828"], distance_cache["J828"], result)

    for radius, budgets in ((5, (54, 55)), (10, (22, 23))):
        for budget in budgets:
            result = solve_pmedian(distance_cache["J300"], weights, budget,
                                   evaluation_radius_km=radius, time_limit=args.time_limit)
            row = export(f"pmedian_J300_R{radius}_K{budget}", "J300", candidate_cache["J300"], distance_cache["J300"], result)
            reference = curves[(curves.scope == "main") & (curves.method == "P-Median")
                               & (curves.radius_km == radius) & (curves.K_target == budget)]
            if len(reference) != 1:
                raise ValueError("Missing p-median reference curve row")
            r = reference.iloc[0]
            gap = (100*(float(r.weighted_avg_distance_km)*total-row["primal_objective"])/row["primal_objective"]
                   if row["solver_certified_optimal"] else None)
            pmedian_comparisons.append({
                "job_id": row["job_id"], "R": radius, "K": budget, "candidate_set": "J300",
                "heuristic_covered_orders": int(r.covered_orders),
                "exact_covered_orders": row["covered_orders"],
                "heuristic_mean_km": float(r.weighted_avg_distance_km),
                "exact_mean_km": row["weighted_avg_distance_km"],
                "distance_objective_gap_pct": 0.0 if gap is not None and abs(gap) < 1e-10 else gap,
                "same_distance_objective_K_candidates": True,
                "note": "Does not establish the first feasible K of the sequence of exact p-median optima",
            })

    for filename, frames, columns in (
            ("exact_facilities.csv", facilities, ["job_id", "candidate_set", "facility_id"]),
            ("exact_assignments.csv", assignments, ["job_id", "candidate_set", "postal_prefix"]),
            ("exact_municipalities.csv", municipalities, ["job_id", "candidate_set", "city_norm"])):
        (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)).to_csv(out/filename, index=False)
    comparisons = []
    lookup = {(r["candidate_set"], r["radius_km"]): r for r in rows if r["job_id"].startswith("partial_")}
    for _, reference in selections[(selections.status == "selected") &
                                  selections.method.isin(["P-Median", "MCLP"])].iterrows():
        name = "J300" if reference.scope == "main" else "J828"
        certified = lookup[(name, reference.radius_km)]
        optimum = certified["K"] if certified["solver_certified_optimal"] else None
        comparisons.append({
            "method": reference.method, "scope": reference.scope, "R": reference.radius_km,
            "candidate_set": name, "selected_K": int(reference.K_selected),
            "coverage_cardinality_optimum": optimum,
            "cardinality_excess_pct": 100*(int(reference.K_selected)-optimum)/optimum if optimum else None,
            "same_candidate_space": True,
            "note": "Coverage-cardinality benchmark; not a p-median distance-objective gap",
        })
    pd.DataFrame(comparisons).to_csv(out/"cardinality_comparisons.csv", index=False)
    pd.DataFrame(pmedian_comparisons).to_csv(out/"pmedian_comparisons.csv", index=False)
    assert {name: sha(path) for name, path in paths.items()} == input_hashes
    assert {p.name: sha(p) for p in code_paths} == metadata["code_sha256"]
    metadata.update({
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_runtime_s": time.perf_counter()-started_all,
        "run_state": "complete", "result_count": len(rows),
        "certified_optimal_count": sum(r["solver_certified_optimal"] for r in rows),
        "certified_infeasible_count": sum(r["certified_infeasible"] for r in rows),
        "input_files_unchanged": True,
    })
    json_write(out/"exact_results.json", rows)
    pd.DataFrame(rows).to_csv(out/"exact_results.csv", index=False)
    json_write(out/"candidate_sets.json", set_metadata)
    json_write(out/"exact_metadata.json", metadata)
    metadata["output_sha256"] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "exact_metadata.json"}
    json_write(out/"exact_metadata.json", metadata)
    print(f"Complete: {len(rows)} exact references in {out}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO/"data")
    parser.add_argument("--reference-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO/"data/v22_exact")
    parser.add_argument("--time-limit", type=float, default=300)
    args = parser.parse_args()
    args.reference_dir = (args.reference_dir or args.data_dir/"service_selection").resolve()
    if not np.isfinite(args.time_limit) or args.time_limit <= 0:
        parser.error("--time-limit must be positive and finite")
    try:
        run(args)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
