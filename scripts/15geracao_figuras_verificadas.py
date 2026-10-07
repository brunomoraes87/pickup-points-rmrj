"""Publication figures from frozen main networks and certified v23 profiles.

No fitting or optimization. Plot positions use EPSG:31983; the reported service
distances remain Haversine. Direct segments do not represent routes or access.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import shape


def hashed(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def haversine(first, second):
    a, b = np.radians(first), np.radians(second)
    h = np.sin((a[:, None, 0]-b[None, :, 0])/2)**2 + np.cos(a[:, None, 0])*np.cos(b[None, :, 0])*np.sin((a[:, None, 1]-b[None, :, 1])/2)**2
    return 12742.0176*np.arctan2(np.sqrt(np.clip(h, 0, 1)), np.sqrt(np.clip(1-h, 0, 1)))


def pt(value, digits=2):
    return f"{value:.{digits}f}".replace(".", ",")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refusing to overwrite profile figures")
    output.mkdir(parents=True, exist_ok=True)
    profiles = args.profiles.resolve()
    manifest_path, verification_path = profiles/"manifest.json", profiles/"independent_verification.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified = json.loads(verification_path.read_text(encoding="utf-8"))
    if not verified["passed"] or verified["manifest_sha256"] != hashed(manifest_path):
        raise ValueError("Certified profile verification is absent or stale")
    source_paths = {name: args.repo_root/entry["repo_relative"] for name, entry in manifest["inputs"].items()}
    input_hashes = {str(manifest_path): hashed(manifest_path), str(verification_path): hashed(verification_path)}
    for name in ("demand", "main_facilities", "geometry", "scope", "orders"):
        path = source_paths[name]
        if hashed(path) != manifest["inputs"][name]["sha256"]:
            raise ValueError("Frozen plotting source changed: "+name)
        input_hashes[str(path)] = hashed(path)
    table_path = profiles/"all_network_profiles.csv"
    if hashed(table_path) != manifest["output_hashes"]["all_network_profiles.csv"]:
        raise ValueError("Profile table changed")
    input_hashes[str(table_path)] = hashed(table_path)
    table = pd.read_csv(table_path)
    demand = pd.read_csv(source_paths["demand"])
    coords, weights = demand[["lat", "lng"]].to_numpy(), demand.n_pedidos.to_numpy()
    facilities = pd.read_csv(source_paths["main_facilities"])
    geometry = json.loads(source_paths["geometry"].read_text(encoding="utf-8-sig"))
    scope = json.loads(source_paths["scope"].read_text(encoding="utf-8-sig"))
    geoms = [shape(f["geometry"]) for f in geometry["features"] if str(f["properties"]["codarea"]) in scope["municipality_codes"]]
    transform = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)

    def xy(points):
        x, y = transform.transform(points[:, 1], points[:, 0])
        return np.column_stack([x/1000, y/1000])

    boundaries = []
    for geom in geoms:
        for polygon in geom.geoms if geom.geom_type == "MultiPolygon" else [geom]:
            for ring in [polygon.exterior, *polygon.interiors]:
                lnglat = np.asarray(ring.coords)
                x, y = transform.transform(lnglat[:, 0], lnglat[:, 1])
                boundaries.append(np.column_stack([x/1000, y/1000]))
    all_boundaries = np.concatenate(boundaries)
    lower, upper = all_boundaries.min(axis=0)-4, all_boundaries.max(axis=0)+4
    cases = [("main_Agglomerative-ward_R3", "Ward — principal", "Ward principal", "#0077BB"),
             ("J825_R3_T8", "J825 — máximo ≤ 8 km", "J825 T=8", "#33BBEE"),
             ("main_Agglomerative-average_R3", "Average — principal", "Average principal", "#EE7733"),
             ("J825_R3_T4p65", "J825 — máximo ≤ 4,65 km", "J825 T=4,65", "#CC3311")]
    plotted, network_data, checks, extremes = [], [], [], []
    for network_id, title, short, colour in cases:
        row = table.loc[table.network_id == network_id].iloc[0]
        if network_id.startswith("main_"):
            selected = facilities[(facilities.scope == "main") & (facilities.method == row.method) & (facilities.radius_km == 3)]
            centres = selected[["lat", "lng"]].to_numpy()
        else:
            path = profiles/"networks"/(network_id+".npz")
            if hashed(path) != manifest["output_hashes"][str(path.relative_to(profiles)).replace("\\", "/")]:
                raise ValueError("Certified network changed: "+network_id)
            input_hashes[str(path)] = hashed(path)
            with np.load(path, allow_pickle=False) as saved:
                centres = saved["selected_centers"]
        matrix = haversine(coords, centres)
        nearest = matrix.argmin(axis=1)
        distances = matrix.min(axis=1)
        order = np.argsort(distances, kind="stable")
        p99 = distances[order[np.searchsorted(np.cumsum(weights[order]), (int(weights.sum())*99+99)//100)]]
        recalculated = {"K": len(centres), "weighted_avg_distance_km": np.average(distances, weights=weights),
                        "p99_empirical_km": p99, "max_distance_km": max(distances),
                        "covered_orders": int(weights[distances <= 3].sum())}
        for key, value in recalculated.items():
            checks.append({"network_id": network_id, "field": key, "passed": bool(np.isclose(row[key], value, rtol=1e-10, atol=1e-9))})
        longest = np.argsort(-distances, kind="stable")[:3]
        for rank, position in enumerate(longest, 1):
            extremes.append({"network_id": network_id, "rank": rank,
                             "demand_position": int(position), "postal_prefix": int(demand.iloc[position].customer_zip_code_prefix),
                             "n_orders": int(weights[position]), "facility_id": int(nearest[position]),
                             "distance_km": float(distances[position]),
                             "demand_lat": coords[position, 0], "demand_lng": coords[position, 1],
                             "facility_lat": centres[nearest[position], 0], "facility_lng": centres[nearest[position], 1]})
        network_data.append((row, title, short, colour, xy(centres), nearest, distances, longest))
        plotted.append({"network_id": network_id, "label": short, **{key: row[key] for key in
                       ("K", "weighted_avg_distance_km", "p99_empirical_km", "max_distance_km", "municipalities_below80", "covered_orders", "coverage_pct")}})
    if not all(check["passed"] for check in checks):
        raise ValueError("Plotted profile does not match the certified metrics")
    pd.DataFrame(plotted).to_csv(output/"valores_plotados.csv", index=False)
    pd.DataFrame(extremes).to_csv(output/"tres_maiores_deslocamentos.csv", index=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
                         "font.size": 12, "pdf.fonttype": 42})
    fig, axes = plt.subplots(2, 2, figsize=(11.8, 10.4), constrained_layout=False)
    demand_xy = xy(coords)
    sizes = 5+4*np.log1p(weights)
    for panel, (ax, data) in enumerate(zip(axes.ravel(), network_data), 1):
        row, title, short, colour, centres_xy, nearest, distances, longest = data
        for border in boundaries:
            ax.plot(border[:, 0], border[:, 1], color="0.75", linewidth=.55, zorder=0)
        inside = distances <= 3
        ax.scatter(demand_xy[inside, 0], demand_xy[inside, 1], s=sizes[inside], color="#6EA6BF", alpha=.72, linewidths=0, zorder=2)
        ax.scatter(demand_xy[~inside, 0], demand_xy[~inside, 1], s=sizes[~inside], color="#B85158", alpha=.9, linewidths=0, zorder=3)
        ax.scatter(centres_xy[:, 0], centres_xy[:, 1], s=28, marker="^", color="#E69F00", edgecolor="0.15", linewidths=.4, zorder=4)
        for rank, position in enumerate(longest, 1):
            start, end = demand_xy[position], centres_xy[nearest[position]]
            ax.plot([start[0], end[0]], [start[1], end[1]], color="#A00036", linestyle="--", linewidth=1.4, zorder=5)
            middle = (start+end)/2
            label_offset = ((3, 14) if rank == 2 else (3, -14) if rank == 3 else (3, 0)) if panel == 4 else (3, (rank-2)*11)
            ax.annotate(f"{rank}: {pt(distances[position])} km", xy=middle,
                        xytext=label_offset, textcoords="offset points", fontsize=10.5,
                        color="#780025", bbox={"facecolor": "white", "alpha": .86, "edgecolor": "none", "pad": .4}, zorder=7)
        ax.set_xlim(lower[0], upper[0]); ax.set_ylim(lower[1], upper[1]); ax.set_aspect("equal")
        ax.tick_params(labelsize=11)
        ax.set_xlabel("Leste UTM (km)", fontsize=12)
        ax.set_ylabel("Norte UTM (km)", fontsize=12)
        ax.set_title(f"({panel}) {title}\nK={int(row.K)} | média={pt(row.weighted_avg_distance_km)} km | P99={pt(row.p99_empirical_km)} km\n"
                     f"máximo={pt(row.max_distance_km)} km | municípios <80%={int(row.municipalities_below80)}", fontsize=13.5, pad=10, loc="left")
        ax.grid(alpha=.15, linewidth=.5)
    legend = [Line2D([], [], marker="o", linestyle="none", color="#6EA6BF", label="Prefixo a ≤3 km"),
              Line2D([], [], marker="o", linestyle="none", color="#B85158", label="Prefixo a >3 km"),
              Line2D([], [], marker="^", linestyle="none", markeredgecolor="0.15", color="#E69F00", label="Instalação"),
              Line2D([], [], linestyle="--", color="#A00036", label="Três maiores deslocamentos")]
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.5, .034), ncol=2, fontsize=12, frameon=False)
    fig.suptitle("Redes com cobertura global ≥95% no cenário de 3 km", fontsize=17, y=.985)
    fig.subplots_adjust(left=.09, right=.98, top=.88, bottom=.16, hspace=.52, wspace=.27)
    fig.savefig(output/"16_mapas_perfis_R3_v23.png", dpi=210)
    fig.savefig(output/"16_mapas_perfis_R3_v23.pdf")
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(12.6, 8.1))
    specs = [("K", "Quantidade de instalações", "instalações", 0),
             ("weighted_avg_distance_km", "Deslocamento médio", "km", 2),
             ("p99_empirical_km", "P99 empírico ponderado", "km", 2),
             ("max_distance_km", "Maior deslocamento", "km", 2),
             ("municipalities_below80", "Municípios abaixo de 80%", "municípios", 0)]
    for ax, (field, title, unit, digits) in zip(axes.ravel(), specs):
        values = [record[field] for record in plotted]
        ax.barh(np.arange(4), values, color=[data[3] for data in network_data], height=.64)
        ax.set_yticks(np.arange(4), ["Ward", "J825 (8 km)", "Average", "J825 (4,65 km)"], fontsize=12)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=13.5, pad=10)
        ax.set_xlabel(unit, fontsize=12)
        limit = max(values)*1.25 if max(values) else 1
        ax.set_xlim(0, limit)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, position: f"{value:g}".replace(".", ",")))
        for position, value in enumerate(values):
            ax.text(value+limit*.025, position, pt(value, digits), va="center", fontsize=12)
        ax.grid(axis="x", alpha=.17)
        ax.set_axisbelow(True)
    axes.ravel()[-1].axis("off")
    note = ("Menor K e máximo\npodem coexistir com\nmédia ou P99 maiores.\n\nAvaliar também a\ncobertura municipal.\n\nJ825 minimiza K.")
    note_artist = axes.ravel()[-1].text(.03, .92, note, transform=axes.ravel()[-1].transAxes,
                                       va="top", fontsize=13, linespacing=1.2)
    fig.suptitle("Compensações entre os quatro perfis de atendimento — R=3 km", fontsize=17, y=.985)
    fig.subplots_adjust(left=.16, right=.97, bottom=.085, top=.88, wspace=.90, hspace=.58)
    fig.canvas.draw()
    note_extent = note_artist.get_window_extent(fig.canvas.get_renderer())
    if note_extent.x1 > fig.bbox.x1-5 or note_extent.y0 < 5:
        raise ValueError("Interpretation note would be clipped by the figure canvas")
    fig.savefig(output/"17_comparacao_perfis_R3_v23.png", dpi=210)
    fig.savefig(output/"17_comparacao_perfis_R3_v23.pdf")
    plt.close(fig)
    caption = ("Figura — Redes principais de Ward e Average e alternativas certificadas J825 no cenário R=3 km. "
               "A área dos pontos cresce com a quantidade de pedidos representados por cada prefixo; as cores indicam o atendimento pelo ponto de retirada mais próximo. "
               "Os três maiores deslocamentos por painel aparecem como segmentos diretos, sem interpretação viária. "
               "A geometria é a união administrativa dos 22 municípios (IBGE 2022), sem certificação de terra seca, comércio ou acesso. "
               "A projeção EPSG:31983 é usada apenas para exibição; as distâncias e percentis continuam Haversine, ponderados pelos pedidos. "
               "As duas redes J825 minimizam quantidade sob cobertura global de 95% e máximo de 8/4,65 km; as demais métricas descrevem o ótimo particular exportado.\n\n"
               "Figura — Quantidade, média, P99, máximo e número de municípios abaixo de 80% para as mesmas quatro redes. "
               "Os eixos mostram valores absolutos, com escalas próprias e zero; 80% é um diagnóstico municipal, não critério de seleção.\n")
    output.joinpath("legendas_figuras.txt").write_text(caption, encoding="utf-8")
    result = {"script_sha256": hashed(__file__), "passed": all(check["passed"] for check in checks),
              "input_hashes": input_hashes, "checks": checks, "network_ids": [data[0].network_id for data in network_data],
              "display_crs": "EPSG:31983", "service_distance": "Haversine radius6371.0088km", "shared_map_limits_km": [lower.tolist(), upper.tolist()],
              "output_hashes": {p.name: hashed(p) for p in output.iterdir() if p.is_file()}}
    output.joinpath("manifesto_figuras.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "checks": len(checks), "figures": 2, "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
