"""Reproducible figures; K=70 is a reference scenario, not an optimum."""
import argparse
import colorsys
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from methods import (method_agglomerative, method_kmeans_weighted,
                     method_pmedian_heuristic, method_mclp_heuristic,
                     haversine_to_centers, evaluate)

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
FIGS = REPO / "figures"
CANDIDATES = 300
BOUNDARIES = []
NAMES = ["KMeans-weighted", "Agglomerative-ward", "Agglomerative-complete",
         "Agglomerative-average", "P-Median", "MCLP-R3km"]
COLORS = dict(zip(NAMES, ["#238b45", "#2171b5", "#756bb1", "#8c564b", "#cb181d", "#e6550d"]))
plt.rcParams.update({"font.family": "DejaVu Sans", "figure.dpi": 140})

def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGS / name, dpi=160, bbox_inches="tight")
    plt.close(fig)

def geo_axis(ax, title):
    for ring in BOUNDARIES:
        xy = np.asarray(ring)
        ax.plot(xy[:, 0], xy[:, 1], color="#a0a0a0", lw=.45, zorder=0)
    ax.set(xlabel="Longitude", ylabel="Latitude", title=title,
           xlim=(-44.15, -42.45), ylim=(-23.15, -22.15))
    ax.set_aspect(1 / np.cos(np.radians(-22.7)))
    ax.set_xticks([-44.0, -43.5, -43.0, -42.5])
    ax.grid(alpha=.18, lw=.4)
    ax.tick_params(labelsize=11)
    ax.xaxis.label.set_size(12)
    ax.yaxis.label.set_size(12)
    ax.title.set_size(13)

def models(df, k):
    top = df.nlargest(min(CANDIDATES, len(df)), "n_pedidos").index.values
    return [
        (NAMES[0], method_kmeans_weighted(df, n_clusters=k)),
        (NAMES[1], method_agglomerative(df, n_clusters=k, linkage="ward")),
        (NAMES[2], method_agglomerative(df, n_clusters=k, linkage="complete")),
        (NAMES[3], method_agglomerative(df, n_clusters=k, linkage="average")),
        (NAMES[4], method_pmedian_heuristic(df, p=k, candidates_idx=top)),
        (NAMES[5], method_mclp_heuristic(df, p=k, radius_km=3, candidates_idx=top)),
    ]

def map_panel(ax, df, labels, centers, title):
    # Every facility receives a separate color; IDs are local to each method.
    palette = [colorsys.hsv_to_rgb((i * .61803398875) % 1, .72, .72)
               for i in range(len(centers))]
    point_colors = [palette[int(i)] if i >= 0 else (.6, .6, .6) for i in labels]
    geo_axis(ax, title)
    ax.scatter(df.lng, df.lat, s=np.sqrt(df.n_pedidos)*3,
               c=point_colors, alpha=.75, linewidths=0, zorder=2)
    ax.scatter(centers[:, 1], centers[:, 0], s=26, marker="x",
               c="#111111", linewidths=.9, zorder=3)

def figures_maps(df):
    for k in (15, 70):
        fig, axes = plt.subplots(3, 2, figsize=(10, 11))
        for ax, (name, (native, centers, runtime)) in zip(axes.flat, models(df, k)):
            d = haversine_to_centers(df.lat.values, df.lng.values, centers[:, 0], centers[:, 1])
            nearest = d.argmin(axis=1)
            map_panel(ax, df, nearest, centers, f"{name} | {len(centers)} pontos")
        fig.suptitle(f"Atribuição ao ponto mais próximo | referência K={k}\n"
                     "Demanda por prefixo de CEP; cruzes: instalações propostas; limites: IBGE",
                     fontsize=13)
        save(fig, f"04_mapas_K{k}.png")

def exploration(df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    geo_axis(axes[0], "Demanda após a checagem de coordenadas")
    axes[0].scatter(df.lng, df.lat, s=np.sqrt(df.n_pedidos)*4,
                    c=df.n_pedidos, cmap="YlOrRd", alpha=.7, linewidths=.2, edgecolors="#444")
    axes[1].hist(df.n_pedidos, bins=50, color="#2171b5", edgecolor="white")
    axes[1].set(xlabel="Pedidos por prefixo de CEP", ylabel="Frequência de prefixos",
                yscale="log", title=f"{len(df)} prefixos | {int(df.n_pedidos.sum()):,} pedidos")
    axes[1].grid(alpha=.2)
    save(fig, "01_exploracao_demanda.png")

def result_curves(res):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, radius in zip(axes, (3, 5, 10)):
        for name in NAMES[:-1] + [f"MCLP-R{radius}km"]:
            sub = res[res.method == name].sort_values("K_target")
            color = COLORS.get(name, "#e6550d")
            ax.plot(sub.K_target, sub[f"coverage_{radius}km_%"], "-o",
                    color=color, label=name, ms=4)
        ax.set(xlabel="K solicitado", ylabel="Pedidos no raio (%)",
               title=f"Cobertura a {radius} km", ylim=(0, 102))
        ax.grid(alpha=.2)
        ax.legend(fontsize=7)
    save(fig, "02_cobertura_vs_K.png")
    fig, ax = plt.subplots(figsize=(10, 5))
    for name in NAMES:
        sub = res[res.method == name].sort_values("K_target")
        ax.plot(sub.K_target, sub.weighted_avg_distance_km, "-o",
                label=name, color=COLORS[name], ms=4)
    ax.set(xlabel="K solicitado", ylabel="Distância média por pedido (km)",
           title="Distância ao ponto mais próximo")
    ax.legend(fontsize=8); ax.grid(alpha=.2)
    save(fig, "03_distancia_vs_K.png")
    fig, ax = plt.subplots(figsize=(9, 6))
    for name in NAMES:
        sub = res[res.method == name].sort_values("K_target")
        ax.plot(sub["coverage_3km_%"], sub["coverage_10km_%"], "-o",
                color=COLORS[name], label=name, ms=4)
    ax.set(xlabel="Cobertura a 3 km (%)", ylabel="Cobertura a 10 km (%)",
           title="Cobertura nos cenários testados")
    ax.legend(fontsize=8); ax.grid(alpha=.2)
    save(fig, "05_tradeoff_cobertura.png")

def reference_curves(df):
    top = df.nlargest(min(CANDIDATES, len(df)), "n_pedidos").index.values
    rows = []
    for k in range(10, 161, 10):
        configs = [
            (NAMES[0], method_kmeans_weighted(df, n_clusters=k)),
            (NAMES[1], method_agglomerative(df, n_clusters=k, linkage="ward")),
            (NAMES[5], method_mclp_heuristic(df, p=k, radius_km=3, candidates_idx=top)),
        ]
        for name, (labels, centers, runtime) in configs:
            rows.append({"method": name, "K_target": k, "runtime_s": runtime,
                         **evaluate(df, labels, centers)})
    curves = pd.DataFrame(rows)
    curves.to_csv(DATA / "reference_curves_K10_K160.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for name in (NAMES[0], NAMES[1], NAMES[5]):
        sub = curves[curves.method == name]
        axes[0].plot(sub.K_target, sub["coverage_3km_%"], "-o", label=name, color=COLORS[name], ms=4)
        axes[1].plot(sub.K_target, sub.weighted_avg_distance_km, "-o", label=name, color=COLORS[name], ms=4)
    for ax in axes:
        ax.axvline(70, ls="--", color="#555", lw=1, label="K=70: cenário de referência")
        ax.set_xlabel("K solicitado")
        ax.grid(alpha=.2); ax.legend(fontsize=8)
    axes[0].set(ylabel="Pedidos a até 3 km (%)", title="Cobertura com a ampliação da rede")
    axes[1].set(ylabel="Distância média por pedido (km)", title="Distância com a ampliação da rede")
    save(fig, "07_saturacao_K70.png")

def linkage_comparison(res):
    sub = res[(res.K_target == 70) & res.method.isin(NAMES[1:4])]
    metrics = [
        ("weighted_avg_distance_km", "Média (km)"),
        ("coverage_3km_%", "Cobertura 3 km (%)"),
        ("p95_distance_km", "P95 por pedido (km)"),
        ("p99_distance_km", "P99 por pedido (km)"),
        ("max_distance_km", "Máximo (km)"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(10, 6.5))
    axes.flat[-1].axis("off")
    labels = ["Ward", "complete", "average"]
    vals = sub.set_index("method").reindex(NAMES[1:4])
    for ax, (col, title) in zip(axes.flat, metrics):
        ax.bar(labels, vals[col], color=[COLORS[n] for n in NAMES[1:4]])
        for i, value in enumerate(vals[col]):
            ax.text(i, value, f"{value:.2f}", ha="center", va="bottom", fontsize=11)
        ax.set_title(title, fontsize=12)
        ax.tick_params(axis="x", labelrotation=20)
        ax.grid(axis="y", alpha=.2)
        ax.margins(y=.18)
    fig.suptitle("Linkages em K=70 | atribuição ao ponto mais próximo", fontsize=13)
    save(fig, "08_dominancia_linkages.png")

def assignment_diagnostic():
    assignments = pd.read_csv(DATA / "assignments_K70.csv")
    facilities = pd.read_csv(DATA / "facilities_K70.csv")
    chosen = ["KMeans-weighted", "Agglomerative-ward"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 12))
    examples = []
    for row, name in enumerate(chosen):
        sub = assignments[assignments.method == name].copy().reset_index(drop=True)
        fs = facilities[facilities.method == name].sort_values("facility_id")
        centers = fs[["lat", "lng"]].to_numpy()
        for col, label_col in enumerate(("native_label", "nearest_facility")):
            map_panel(axes[row, col], sub, sub[label_col].to_numpy(), centers,
                      f"{name} | {'grupos nativos' if col == 0 else 'ponto mais próximo'}")
        sub["distance_difference_km"] = sub.native_distance_km - sub.distance_km
        far = sub[sub.distance_difference_km > 1e-6].nlargest(3, "distance_difference_km")
        for _, point in far.iterrows():
            native = int(point.native_label)
            if native < 0: continue
            axes[row, 0].plot([point.lng, centers[native, 1]],
                              [point.lat, centers[native, 0]], color="#d00000", lw=1)
            examples.append(point.to_dict())
    fig.suptitle("Grupos de formação e atribuição operacional\n"
                 "Linhas vermelhas: três maiores reduções de distância ao trocar a atribuição",
                 fontsize=12)
    save(fig, "09_grupos_nativos_vs_ponto_proximo.png")
    pd.DataFrame(examples).to_csv(DATA / "native_assignment_examples.csv", index=False)

def main():
    global DATA, FIGS, CANDIDATES, BOUNDARIES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--figures-dir", type=Path, default=FIGS)
    parser.add_argument("--candidates", type=int, default=300)
    args = parser.parse_args()
    DATA, FIGS, CANDIDATES = args.data_dir, args.figures_dir, args.candidates
    FIGS.mkdir(parents=True, exist_ok=True)
    scope = json.loads((DATA / "geography/scope.json").read_text(encoding="utf-8-sig"))
    geo = json.loads((DATA / "geography/rj_municipios_ibge.geojson").read_text(encoding="utf-8-sig"))
    for feature in geo["features"]:
        code = str(feature["properties"]["codarea"])
        if code not in [str(c) for c in scope["municipality_codes"]]: continue
        geom = feature["geometry"]
        polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        BOUNDARIES.extend(ring for poly in polygons for ring in poly)
    df = pd.read_csv(DATA / "demanda_por_cep.csv")
    res = pd.read_csv(DATA / "results_full.csv")
    for name, fn in [
        ("exploração", lambda: exploration(df)),
        ("curvas comparativas", lambda: result_curves(res)),
        ("mapas", lambda: figures_maps(df)),
        ("curvas de referência", lambda: reference_curves(df)),
        ("comparação dos linkages", lambda: linkage_comparison(res)),
        ("grupos nativos", assignment_diagnostic),
    ]:
        print(f"Gerando {name}...", flush=True)
        fn()
    print(f"Figuras e tabelas auxiliares salvas em {FIGS}", flush=True)

if __name__ == "__main__":
    main()
