"""Standalone overlays of observed curves and independently evaluated exact solutions.

This helper never imports scientific code from the manuscript repository. It reads
completed outputs only, recomputes distances to the exported exact facilities,
and separates candidate sets. A cardinality optimum is not a distance optimum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

EARTH_KM = 6371.0088
METRICS = [
    ("coverage_pct", "Cobertura postal (%)"),
    ("weighted_avg_distance_km", "Distância média (km)"),
    ("p99_empirical_km", "P99 empírico (km)"),
    ("max_distance_km", "Distância máxima (km)"),
    ("zero_coverage_municipalities", "Municípios com cobertura 0%"),
]
METHOD_STYLE = {
    "KMeans-weighted": ("K-Means — semente 42", "#2171b5"),
    "Agglomerative-ward": ("Ward", "#e6550d"),
    "Agglomerative-complete": ("Complete", "#31a354"),
    "Agglomerative-average": ("Average", "#756bb1"),
    "P-Median": ("P-Median — heurística", "#cb181d"),
    "MCLP": ("MCLP — heurística", "#008b8b"),
}
CANDIDATE_STYLE = {
    "J300_reverse": ("#b15928", "X"),
    "J825": ("#1b9e77", "D"),
    "J828_grid1000": ("#7570b3", "v"),
    "J825_grid1000": ("#e7298a", "^"),
    "J828_grid500": ("#66a61e", "s"),
    "J825_grid500": ("#e6ab02", "P"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def truth(value) -> bool:
    return str(value).lower() == "true"


def haversine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Independent all-pairs distance implementation, latitude then longitude."""
    lat_a, lon_a = np.deg2rad(a).T
    lat_b, lon_b = np.deg2rad(b).T
    dlat = lat_b[None, :] - lat_a[:, None]
    dlon = lon_b[None, :] - lon_a[:, None]
    h = np.sin(dlat / 2) ** 2 + np.cos(lat_a[:, None]) * np.cos(lat_b[None, :]) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arctan2(np.sqrt(np.clip(h, 0, 1)), np.sqrt(np.clip(1-h, 0, 1)))


def quantile(d: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(d, kind="stable")
    cumulative = np.cumsum(weights[order])
    target = int(np.ceil(q * int(weights.sum())))
    return float(d[order[np.searchsorted(cumulative, target, side="left")]])


def independent_exact_metrics(demand: pd.DataFrame, orders: pd.DataFrame,
                              results: pd.DataFrame, facilities: pd.DataFrame):
    prefix = "customer_zip_code_prefix"
    demand[prefix] = demand[prefix].astype(str).str.zfill(5)
    orders[prefix] = orders[prefix].astype(str).str.zfill(5)
    weights = demand.n_pedidos.to_numpy(dtype=np.int64)
    counts = pd.crosstab(orders[prefix], orders.city_norm).reindex(demand[prefix], fill_value=0).to_numpy(dtype=np.int64)
    if orders.order_id.duplicated().any() or not np.array_equal(counts.sum(axis=1), weights):
        raise ValueError("Order weights/municipalities do not match the exact demand.")
    total = int(weights.sum())
    required = int(np.ceil(.95 * total))
    coords = demand[["lat", "lng"]].to_numpy(float)
    output, checks, omissions = [], [], []
    for row in results.to_dict("records"):
        job_id = row["job_id"]
        centers = facilities[facilities.job_id == job_id][["lat", "lng"]].to_numpy(float)
        certified = truth(row["solver_certified_optimal"])
        if not certified or not truth(row["has_primal_solution"]):
            omissions.append({"job_id": job_id, "candidate_set": row["candidate_set"],
                              "radius_km": float(row["radius_km"]), "status": int(row["status"]),
                              "certified_infeasible": truth(row["certified_infeasible"]),
                              "candidate_ceiling_orders": row.get("candidate_ceiling_orders"),
                              "required_orders": required, "message": str(row["message"]),
                              "reason": "No certified finite optimum; no scientific point fabricated."})
            continue
        if len(centers) != int(row["K"]) or not len(centers):
            raise ValueError(f"Exact center count mismatch: {job_id}")
        distances = haversine(coords, centers).min(axis=1)
        radius = float(row["radius_km"])
        covered = distances <= radius
        values = {
            "job_id": job_id, "candidate_set": row["candidate_set"], "problem": row["problem"],
            "radius_km": radius, "K": len(centers), "status": int(row["status"]),
            "solver_certified_optimal": certified,
            "mandatory_radius_km": row.get("mandatory_radius_km"),
            "total_orders": total, "required_orders": required,
            "covered_orders": int(weights[covered].sum()),
            "coverage_pct": 100 * int(weights[covered].sum()) / total,
            "weighted_avg_distance_km": float(np.average(distances, weights=weights)),
            "median_empirical_km": quantile(distances, weights, .5),
            "p95_empirical_km": quantile(distances, weights, .95),
            "p99_empirical_km": quantile(distances, weights, .99),
            "max_distance_km": float(distances.max()),
            "zero_coverage_municipalities": int((counts[covered].sum(axis=0) == 0).sum()),
            "candidate_space_only": True, "profile_is_unique_or_distance_optimal": False,
        }
        for calculated, original in [
            ("covered_orders", "covered_orders"), ("coverage_pct", "coverage_pct"),
            ("weighted_avg_distance_km", "weighted_avg_distance_km"),
            ("median_empirical_km", "median_empirical_km"),
            ("p95_empirical_km", "p95_empirical_km"),
            ("p99_empirical_km", "p99_empirical_km"),
            ("max_distance_km", "max_distance_km"),
            ("zero_coverage_municipalities", "municipalities_zero"),
        ]:
            expected = float(row[original])
            observed = float(values[calculated])
            passed = bool(np.isclose(observed, expected, atol=1e-8, rtol=1e-10))
            checks.append({"job_id": job_id, "field": calculated, "observed": observed,
                           "expected": expected, "absolute_difference": abs(observed-expected), "passed": passed})
            if not passed:
                raise ValueError(f"Independent exact metric differs: {job_id}/{calculated}")
        output.append(values)
    return pd.DataFrame(output), checks, omissions


def exact_marker(row):
    if row["candidate_set"] in CANDIDATE_STYLE:
        return CANDIDATE_STYLE[row["candidate_set"]]
    if row["problem"] == "pmedian":
        return "#b30000", "*"
    if row["problem"] == "maximal_cover":
        return "#54278f", "s"
    if pd.notna(row.get("mandatory_radius_km")):
        return "#8c510a", "^"
    return "#222222", "D"


def plots(curves, exact, omissions, out_dir):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.titlesize": 10, "axes.labelsize": 9})
    figures = []
    rows = [
        ("continuous", "Centros contínuos\nCurvas observadas;\nsem ótimo contínuo"),
        ("J300", "J300 principal\nMesmos 300 candidatos"),
        ("J828", "J828 postal\nMesmos 828 candidatos"),
        ("alternative", "Outros conjuntos J\nPontos exatos separados\npor cor e marcador"),
    ]
    for radius in sorted(curves.radius_km.unique()):
        sub = curves[curves.radius_km == radius]
        refs = exact[exact.radius_km == radius]
        # Fixed margins prevent multi-line row notes from pushing the title off
        # the canvas in small-K scenarios under constrained_layout.
        fig, axes = plt.subplots(4, 5, figsize=(18.5, 14))
        fig.suptitle(f"Curvas observadas e referências MILP — R = {radius:g} km\n"
                     "K = instalações; demanda postal ponderada por pedidos; atribuição à instalação mais próxima\n"
                     "Pontos MILP: status 0, ótimo certificado no conjunto J indicado; outros indicadores podem variar entre ótimos",
                     fontsize=13, weight="bold", y=.98)
        for row_idx, (space, row_label) in enumerate(rows):
            curve_space = sub[sub.comparison_space == space]
            ref_space = refs[refs.candidate_set == space] if space in ("J300", "J828") else (
                refs[~refs.candidate_set.isin(["J300", "J828"])] if space == "alternative" else refs.iloc[:0])
            x_values = list(curve_space.K.to_numpy(float)) + list(ref_space.K.to_numpy(float))
            xmax = max(x_values) if x_values else 1
            for col, (metric, title) in enumerate(METRICS):
                ax = axes[row_idx, col]
                ax.grid(alpha=.2, lw=.6)
                if row_idx == 0:
                    ax.set_title(title, pad=10)
                if col == 0:
                    ax.set_ylabel(row_label, fontsize=10, labelpad=16)
                for method, group in curve_space.groupby("method", sort=True):
                    label, color = METHOD_STYLE[method]
                    group = group.sort_values("K")
                    ax.plot(group.K, group[metric], color=color, lw=1.35, label=label, alpha=.9)
                for row in ref_space.to_dict("records"):
                    color, marker = exact_marker(row)
                    ax.scatter(row["K"], row[metric], s=70 if marker == "*" else 46,
                               marker=marker, color=color, edgecolor="white", linewidth=.6, zorder=5)
                if metric == "coverage_pct":
                    ax.axhline(95, color="#777777", ls="--", lw=.8)
                    ax.set_ylim(0, 102)
                elif metric == "zero_coverage_municipalities":
                    ax.set_ylim(-.6, 22.6)
                    ax.set_yticks([0, 5, 10, 15, 20])
                else:
                    allvals = list(sub[metric].dropna()) + list(refs[metric].dropna())
                    ax.set_ylim(0, max(allvals)*1.04 if allvals else 1)
                ax.set_xlim(0, xmax*1.035)
                ax.set_xlabel("K (instalações)")
                ax.spines[["top", "right"]].set_visible(False)
                if curve_space.empty and ref_space.empty:
                    ax.text(.5, .5, "Sem solução/curva disponível", transform=ax.transAxes, ha="center", fontsize=8)
            if row_idx in (1, 2, 3):
                tokens = []
                for record in ref_space.to_dict("records"):
                    suffix = ""
                    if pd.notna(record.get("mandatory_radius_km")):
                        suffix = f"; T={record['mandatory_radius_km']:g}"
                    kind = {"partial_cover": "mín.K", "maximal_cover": "máx.cob.", "pmedian": "p-med."}[record["problem"]]
                    item = f"{record['candidate_set']} {kind}{suffix}: K={record['K']}"
                    if item not in tokens:
                        tokens.append(item)
                unavailable = [o for o in omissions if o["radius_km"] == radius and
                               (o["candidate_set"] == space or (space == "alternative" and o["candidate_set"] not in ("J300", "J828")))]
                tokens += [f"{o['candidate_set']} inviável (status {o['status']}): teto {o['candidate_ceiling_orders']:g}/{o['required_orders']} pedidos" for o in unavailable]
                # A compact row note supplies all K/status/sets without overlaid labels.
                axes[row_idx, 2].text(.5, -0.47, "\n".join(" · ".join(tokens[i:i+2]) for i in range(0, len(tokens), 2)),
                                     transform=axes[row_idx, 2].transAxes, ha="center", va="top", fontsize=7,
                                     clip_on=False)
        handles = [Line2D([], [], color=color, lw=1.5, label=label) for label, color in METHOD_STYLE.values()]
        handles += [Line2D([], [], color=color, marker=marker, ls="", label=label, markersize=7) for color, marker, label in [
            ("#222222", "D", "MILP mínimo K"), ("#54278f", "s", "MILP cobertura máxima, K fixo"),
            ("#b30000", "*", "MILP p-mediana, K fixo"), ("#8c510a", "^", "MILP mínimo K e proximidade T")]]
        handles += [Line2D([], [], color=color, marker=marker, ls="", label=name, markersize=6) for name, (color, marker) in CANDIDATE_STYLE.items()]
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .015), ncols=4, fontsize=8, frameon=False)
        fig.subplots_adjust(left=.07, right=.985, top=.85, bottom=.23, hspace=.95, wspace=.20)
        path = out_dir / f"14_referencias_exatas_R{radius:g}.png"
        fig.savefig(path, dpi=180, facecolor="white")
        plt.close(fig)
        figures.append({"file": path.name, "sha256": sha(path), "radius_km": float(radius),
                        "curve_rows": len(sub), "certified_exact_points": len(refs),
                        "note": "Exact distance/municipal profiles are one certified solution, not unique or optimized by those criteria."})
    return figures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--processed-dir", type=Path, help="Optional processed input directory for a figures/results-only preparation tree.")
    args = parser.parse_args()
    root = args.scientific_root.resolve()
    processed = (args.processed_dir or root / "processed").resolve()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    inputs = {
        "curves": root / "results/main/frontier_curves_v22.csv",
        "exact_results": root / "results/exact/exact_results.csv",
        "exact_facilities": root / "results/exact/exact_facilities.csv",
        "demand": processed / "demanda_por_cep.csv",
        "orders": processed / "pedidos_rmrj_geo.csv",
    }
    if any(not p.is_file() for p in inputs.values()):
        raise FileNotFoundError([str(p) for p in inputs.values() if not p.is_file()])
    hashes_before = {name: sha(path) for name, path in inputs.items()}
    curves = pd.read_csv(inputs["curves"])
    results = pd.read_csv(inputs["exact_results"])
    facilities = pd.read_csv(inputs["exact_facilities"])
    demand = pd.read_csv(inputs["demand"], dtype={"customer_zip_code_prefix": str})
    orders = pd.read_csv(inputs["orders"], dtype={"customer_zip_code_prefix": str})
    exact, checks, omissions = independent_exact_metrics(demand, orders, results, facilities)
    figures = plots(curves, exact, omissions, out)
    exact.to_csv(out / "exact_overlay_metrics.csv", index=False)
    plotvalues = pd.concat([curves.assign(source_type="observed_curve"), exact.assign(source_type="certified_exact_reference")], ignore_index=True)
    plotvalues.to_csv(out / "exact_overlay_plotted_values.csv", index=False)
    hashes_after = {name: sha(path) for name, path in inputs.items()}
    if hashes_after != hashes_before:
        raise RuntimeError("An input changed during overlay generation.")
    report = {"passed": all(c["passed"] for c in checks), "n_checks": len(checks),
              "checks": checks, "omitted_no_optimum": omissions,
              "method": "Own vectorized Haversine and integer-weight empirical quantiles; municipality counts from order-level city fields."}
    (out / "exact_overlay_independent_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    manifest = {"source_files": {k: str(v) for k, v in inputs.items()}, "source_hashes": hashes_before,
                "helper_sha256": sha(Path(__file__)), "figures": figures,
                "outputs": {p.name: sha(p) for p in out.glob("*.csv")},
                "interpretation": [
                    "All exact markers have solver_certified_optimal=True and independently matching exported metrics.",
                    "Only J300 curves and J300 references, or J828 curves and J828 references, share a candidate space.",
                    "J300_reverse, J825 and hybrid grids are alternative candidate spaces shown separately; differences are not optimality gaps.",
                    "Partial covering optimizes K, maximal covering optimizes coverage at fixed K, and p-median optimizes mean distance at fixed K.",
                    "Other indicators of an exact solution need not be optimal or identical across multiple optima.",
                    "Administrative candidate filtering is not a dry-land, access or commercial-viability certificate.",
                    "The continuous curves are observed heuristic/cluster solutions; no continuous global optimum is supplied.",
                ]}
    (out / "exact_overlay_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"figures": len(figures), "exact_points": len(exact), "checks": len(checks), "passed": report["passed"]}))


if __name__ == "__main__":
    main()
