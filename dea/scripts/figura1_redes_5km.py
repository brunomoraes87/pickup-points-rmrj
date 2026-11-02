"""Figura 1 do artigo DEA: duas redes do mesmo cenário (R = 5 km), K-Means e p-mediana, com dados da e688d15.
Vírgula decimal, sem título, rótulos curtos.
Uso (na raiz do repositório): python dea/scripts/figura1_redes_5km.py . dea/figuras/figura_1_redes_5km.png
"""
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import shape

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

plt.rcParams.update({"font.family": "Times New Roman", "font.size": 8})
raiz, saida = Path(sys.argv[1]), Path(sys.argv[2])
main = raiz / "data/v22_verified/main"
ass = pd.read_csv(main / "service_assignments.csv")
fac = pd.read_csv(main / "service_facilities.csv")
geo = json.loads((raiz / "data/geography/rj_municipios_ibge.geojson").read_text(encoding="utf-8-sig"))
esc = json.loads((raiz / "data/geography/scope.json").read_text(encoding="utf-8-sig"))
tr = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
R = 5


def xy(lat, lng):
    x, y = tr.transform(np.asarray(lng), np.asarray(lat))
    return np.asarray(x) / 1000, np.asarray(y) / 1000


def br(v, casas=2):
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


casos = [("KMeans-weighted", "(a) K-Means: pontos no centro de cada grupo"),
         ("P-Median", "(b) p-mediana: pontos em centroides de prefixos (J300)")]
fig, eixos = plt.subplots(1, 2, figsize=(6.3, 3.0))
for ax, (metodo, titulo) in zip(eixos, casos):
    for f in geo["features"]:
        if str(f["properties"]["codarea"]) not in esc["municipality_codes"]:
            continue
        g = shape(f["geometry"])
        for p in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            c = np.asarray(p.exterior.coords)
            x, y = xy(c[:, 1], c[:, 0])
            ax.fill(x, y, color="#f2f2f2", ec="#a0a0a0", lw=0.3, zorder=0)
    a = ass[(ass.scope == "main") & (ass.method == metodo) & (ass.radius_km == R)]
    f_ = fac[(fac.scope == "main") & (fac.method == metodo) & (fac.radius_km == R)].set_index("facility_id")
    fx, fy = xy(f_.lat, f_.lng)
    pos = dict(zip(f_.index, zip(fx, fy)))
    px, py = xy(a.lat, a.lng)
    for x0, y0, fid in zip(px, py, a.nearest_facility):
        x1, y1 = pos[fid]
        ax.plot([x0, x1], [y0, y1], color="#b8c4d6", lw=0.25, zorder=1)
    for x, y in zip(fx, fy):
        ax.add_patch(plt.Circle((x, y), R, color="#4a90d9", alpha=0.12, lw=0, zorder=1))
    cob = ~a.outside_R.astype(bool)
    s = 1 + 0.8 * np.sqrt(a.n_pedidos)
    ax.scatter(px[cob], py[cob], s=s[cob], c="#2b6cb0", alpha=0.8, lw=0, zorder=2)
    ax.scatter(px[~cob], py[~cob], s=s[~cob], c="#d64545", alpha=0.9, lw=0, zorder=2)
    ax.scatter(fx, fy, marker="^", s=16, c="black", ec="white", lw=0.4, zorder=3)
    tot, cobertos = a.n_pedidos.sum(), a.loc[cob, "n_pedidos"].sum()
    media = np.average(a.distance_km, weights=a.n_pedidos)
    caixa = (f"K = {len(f_)} pontos\ncobertos: {br(cobertos, 0)} ({br(100 * cobertos / tot, 1)}%)\n"
             f"média: {br(media)} km\nmáxima: {br(a.distance_km.max())} km")
    ax.text(0.02, 0.98, caixa, transform=ax.transAxes, va="top", fontsize=7,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#999", lw=0.5))
    ax.set_title(titulo, fontsize=8)
    ax.set_aspect("equal")
    ax.set_xticks([]), ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_linewidth(0.5)
leg = [Line2D([], [], marker="^", ls="", color="black", ms=5, label="ponto de retirada"),
       Line2D([], [], marker="o", ls="", color="#2b6cb0", ms=4, label="prefixo a até 5 km"),
       Line2D([], [], marker="o", ls="", color="#d64545", ms=4, label="prefixo além de 5 km"),
       Line2D([], [], color="#b8c4d6", lw=1, label="ligação ao ponto mais próximo"),
       Line2D([], [], marker="o", ls="", color="#4a90d9", alpha=0.35, ms=8, label="raio de 5 km")]
fig.legend(handles=leg, loc="lower center", ncol=5, fontsize=7, frameon=False, handletextpad=0.3, columnspacing=1.0)
fig.tight_layout(rect=(0, 0.06, 1, 1), w_pad=0.6)
fig.savefig(saida, dpi=400, bbox_inches="tight", pad_inches=0.03)
print("ok", saida)
