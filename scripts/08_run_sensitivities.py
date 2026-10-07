"""Run the declared v22 sensitivities without changing any input cohort.

Example:
  python scripts/08_run_sensitivities.py --raw-dir PATH --data-dir data --out data/v22_sensitivity
The output folder is signature-locked. Fresh scientific replication uses a new folder.
"""
from pathlib import Path
import argparse
import json
import time
import pandas as pd
from robustness_v22 import (
    POLICY, SEEDS, RADII, METHODS, KM_CONFIG, adjustment_metric, file_sha, object_sha, atomic_json, atomic_csv,
    load_inputs, make_cases, candidate_audit, prefix_diagnostics, SearchRunner,
    run_seed_windows, conservative_comparison, versions_metadata,
)

def scientific_csv_sha(path):
    """Canonical file content after removing the declared nondeterministic clocks."""
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame = frame.drop(columns=[c for c in ("runtime_s", "search_runtime_s") if c in frame], errors="ignore")
    content = frame.to_csv(index=False, lineterminator="\n")
    return __import__("hashlib").sha256(content.encode("utf-8")).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cases", nargs="*", help="Diagnostic subset only; complete status is false")
    parser.add_argument("--skip-seed-windows", action="store_true",
                        help="Diagnostic run only; complete status is false")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    code_files = sorted(p for folder in (repo / "scripts", repo / "tests")
                        for p in folder.rglob("*.py") if "__pycache__" not in p.parts)
    code_hashes = {str(p.relative_to(repo)).replace("\\", "/"): file_sha(p) for p in code_files}
    inputs = [args.raw_dir / ("olist_" + name + "_dataset.csv")
              for name in ("customers", "orders", "geolocation")]
    inputs += [args.data_dir / "demanda_por_cep.csv", args.data_dir / "pedidos_rmrj_geo.csv"]
    inputs += sorted((args.data_dir / "geography").glob("*"))
    input_locations = {}
    input_hashes = {}
    for p in inputs:
        if not p.is_file():
            continue
        prefix = "raw/" if p.parent.resolve() == args.raw_dir.resolve() else "data/"
        relative = p.name if prefix == "raw/" else str(p.relative_to(args.data_dir)).replace("\\", "/")
        logical_name = prefix + relative
        input_hashes[logical_name] = file_sha(p)
        input_locations[logical_name] = str(p.resolve())
    config = dict(radii=RADII, seeds_main=SEEDS, kmeans=KM_CONFIG, seeds_sensitivity=list(range(30)),
                  representative_seed=42, pmedian_max_iter=100, pmedian_swap_epsilon=1e-9,
                  minimum_fraction=.95, metric_main="haversine", earth_radius_km=6371.0088,
                  fit_space_main="degrees", projected_crs="EPSG:31983",
                  search="integers from1; no monotonicity", policy=POLICY,
                  cases_filter=args.cases, skip_seed_windows=args.skip_seed_windows)
    environment = versions_metadata()
    signature_environment = dict(environment)
    signature_environment.pop("executable", None)
    signature = object_sha(dict(input_hashes=input_hashes, code_hashes=code_hashes,
                                config=config, environment=signature_environment))
    args.out.mkdir(parents=True, exist_ok=True)
    metadata_path = args.out / "metadata.json"
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text(encoding="utf-8"))
        if previous["signature_sha256"] != signature:
            raise ValueError("Output signature changed. Use a fresh output directory; checkpoints cannot be mixed.")
    started = time.time()
    metadata = dict(signature_sha256=signature, started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    input_hashes=input_hashes, input_locations=input_locations, code_hashes=code_hashes, config=config, environment=environment,
                    non_scientific_comparison_fields=["runtime_s", "search_runtime_s", "started_utc",
                        "finished_utc", "updated_utc", "elapsed_wall_s", "input_locations",
                        "environment.executable", "raw_output_hashes"],
                    complete=False, complements_pending=["full sensitivity execution", "seed-window execution"],
                    frozen_protocol="Protocol freeze before implementation; not independent prospective preregistration",
                    private_raw_data="Inputs read-only; no download or raw-data modification")
    atomic_json(metadata_path, metadata)
    main_cohort, d16, d22, omitted, union, polygons, scope = load_inputs(args.raw_dir, args.data_dir)
    cases = make_cases(main_cohort, d16, d22, union)
    for co in (main_cohort, d16, d22):
        atomic_csv(args.out / ("orders_" + co.name + ".csv"), co.orders)
    for case in cases:
        derived = case.cohort.df.copy()
        derived["cohort"] = case.cohort.name
        derived["estimator"] = case.cohort.estimator
        derived["evaluation_metric"] = case.metric
        derived["fit_space"] = case.fit_space
        derived["coordinate_interpretation"] = "postal representative, not individual order address"
        atomic_csv(args.out / ("demand_" + case.name + ".csv"), derived)
    metadata["case_configurations"] = [dict(case=c.name, cohort=c.cohort.name,
        estimator=c.cohort.estimator, evaluation_metric=c.metric, fit_space=c.fit_space,
        center_mode=c.center_mode, fit_metrics={m: adjustment_metric(c, m) for m in c.methods})
        for c in cases]
    atomic_json(metadata_path, metadata)
    audit = candidate_audit(cases, main_cohort)
    atomic_csv(args.out / "candidate_sets_audit.csv", audit)
    atomic_csv(args.out / "omission_hypotheses.csv", omitted)
    atomic_csv(args.out / "cohort_summary.csv", pd.DataFrame([
        dict(cohort=co.name, N_orders=len(co.orders), N_prefixes=len(co.df),
             N_unique_buyers=co.orders.customer_unique_id.nunique(),
             required_orders=__import__("math").ceil(.95 * len(co.orders)),
             main_coordinates_preserved=True, interpretation=co.note or "unchanged v21 main")
        for co in (main_cohort, d16, d22)]))
    for co in (d16, d22):
        atomic_csv(args.out / (co.name + "_postal_demand.csv"), co.df)
        atomic_csv(args.out / (co.name + "_order_origin.csv"), co.orders)
    dispersion, extremes = prefix_diagnostics(main_cohort)
    atomic_csv(args.out / "prefix_dispersion.csv", dispersion)
    atomic_csv(args.out / "extreme_record_evidence.csv", extremes)
    if args.cases:
        missing = set(args.cases) - {c.name for c in cases}
        if missing:
            raise ValueError("Unknown case names: " + repr(missing))
        cases = [c for c in cases if c.name in args.cases]
    runner = SearchRunner(args.out, signature, union, polygons)
    for case in cases:
        runner.run_case(case)
    selection = pd.DataFrame(runner.selection)
    # All methods share the declared cohort/candidate condition in these four cases.
    comparison = conservative_comparison(selection, ("main", "geodesic", "geodesic_eval_only", "median", "dedup_full"), METHODS)
    atomic_csv(args.out / "conservative_K_comparison.csv", comparison)
    comparison_projected = conservative_comparison(
        selection, ("main", "geodesic", "geodesic_eval_only", "median", "dedup_full",
                    "projected_inverse", "projected_partition_angular"), ("K-Means", "Ward"))
    atomic_csv(args.out / "conservative_K_comparison_projected.csv", comparison_projected)
    if not args.skip_seed_windows and (not args.cases or "main" in args.cases):
        run_seed_windows(next(c for c in cases if c.name == "main"), selection, runner.store, args.out)
    incomplete = []
    if args.cases:
        incomplete.append("User-requested diagnostic case subset; not a full run")
    if args.skip_seed_windows:
        incomplete.append("30-seed window skipped for diagnostic run")
    elif args.cases and "main" not in args.cases:
        incomplete.append("30-seed window requires main selection")
    current_code_files = sorted(p for folder in (repo / "scripts", repo / "tests")
                                for p in folder.rglob("*.py") if "__pycache__" not in p.parts)
    current_hashes = {str(p.relative_to(repo)).replace("\\", "/"): file_sha(p) for p in current_code_files}
    if current_hashes != code_hashes:
        incomplete.append("Code changed during execution; preserve artifacts, require cold rerun after final freeze")
    output_hashes = {str(p.relative_to(args.out)).replace("\\", "/"): file_sha(p)
                     for p in sorted(args.out.rglob("*.csv"))}
    metadata.update(finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    elapsed_wall_s=time.time() - started, complete=not incomplete,
                    complements_pending=incomplete, N_main_orders=len(main_cohort.orders),
                    N_main_prefixes=len(main_cohort.df), seed_window_runs_expected=1023,
                    selected_and_infeasible_rows=len(selection),
                    extreme_prefixes_gt20km=int(dispersion.extreme_gt20km.sum()),
                    extreme_records_are_deleted=False,
                    geometry_source=scope, raw_output_hashes=output_hashes,
                    scientific_output_hashes={str(p.relative_to(args.out)).replace("\\", "/"): scientific_csv_sha(p)
                                               for p in sorted(args.out.rglob("*.csv"))})
    atomic_json(metadata_path, metadata)
    print(json.dumps(dict(complete=metadata["complete"], selection_rows=len(selection),
                          elapsed_s=metadata["elapsed_wall_s"], out=str(args.out)), ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
