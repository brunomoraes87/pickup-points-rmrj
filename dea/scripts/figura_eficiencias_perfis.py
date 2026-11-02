"""Figura 3 do artigo DEA (Seção 5): eficiência CCR das redes dos métodos nos perfis média e máximo, por raio.
Uso (na raiz do repositório): python dea/scripts/figura_eficiencias_perfis.py dea/resultados/resultados_dea_completos.csv dea/figuras/figura_3_eficiencias_perfis.png
"""
import sys

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

plt.rcParams.update({"font.family": "Times New Roman", "font.size": 8, "axes.linewidth": 0.6})
AZUL, LARANJA, CINZA = "#2a78d6", "#eb6834", "#b4b2a9"
ordem = ["K-Means", "p-mediana", "Ward", "MCLP", "Complete", "Average"]

r = pd.read_csv(sys.argv[1])
m = r[r.tipo == "heurística"].pivot_table(index=["R", "familia"], columns="perfil", values="h")
fig, eixos = plt.subplots(1, 3, figsize=(6.3, 2.4), sharey=True)
for ax, R in zip(eixos, (3, 5, 10)):
    g = m.loc[R].reindex(ordem)
    y = range(len(ordem))
    ax.hlines(y, g.media, g.maximo, color=CINZA, lw=1.2, zorder=1)
    ax.scatter(g.media, y, s=26, color=AZUL, edgecolor="white", lw=0.8, zorder=3)
    ax.scatter(g.maximo, y, s=26, marker="s", color=LARANJA, edgecolor="white", lw=0.8, zorder=3)
    ax.axvline(1, color="#0b0b0b", lw=0.6, ls=(0, (3, 2)), zorder=0)
    ax.set_xlim(0.58, 1.03)
    ax.set_yticks(list(y), ordem)
    ax.invert_yaxis()
    ax.set_title(f"R = {R} km", fontsize=8)
    ax.set_xlabel("Eficiência CCR ($h_o^*$)")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ",")))
    ax.grid(axis="x", color="#e6e5e0", lw=0.5)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
leg = [Line2D([], [], ls="", marker="o", ms=5, color=AZUL, mec="white", label="Perfil média"),
       Line2D([], [], ls="", marker="s", ms=5, color=LARANJA, mec="white", label="Perfil máximo")]
fig.legend(handles=leg, loc="lower center", ncol=2, frameon=False, fontsize=7, bbox_to_anchor=(0.55, -0.03))
fig.tight_layout(rect=(0, 0.07, 1, 1), w_pad=0.8)
fig.savefig(sys.argv[2], dpi=400, bbox_inches="tight", pad_inches=0.03)
print("ok", sys.argv[2])
