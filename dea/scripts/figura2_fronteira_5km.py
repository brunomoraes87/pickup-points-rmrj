"""Figura 2 do artigo DEA: fronteira CCR orientada a inputs em 5 km, perfil máximo, com a projeção do Complete
(redução equiproporcional) e do Average (redução equiproporcional + folga em pontos).
Eixos no formato usual da DEA com dois inputs e um output: input 1/output × input 2/output (por mil pedidos).
Uso (na raiz do repositório): python dea/scripts/figura2_fronteira_5km.py dea/resultados/redes_e_eficiencias_ccr.csv dea/figuras/figura_2_fronteira_5km.png
"""
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator  # noqa: E402

plt.rcParams.update({"font.family": "Times New Roman", "font.size": 8, "axes.linewidth": 0.6})
AZUL, LARANJA, CINZA, TINTA = "#2a78d6", "#eb6834", "#9a9893", "#0b0b0b"
virgula = FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ","))

d = pd.read_csv(sys.argv[1])
g = d[d.R == 5].copy()
g["x1"] = g.K / g.cob * 1000          # pontos por mil pedidos cobertos
g["x2"] = g.maximo / g.cob * 1000     # km de distância máxima por mil pedidos cobertos
ef = g[g.pareto_maximo].drop_duplicates(["x1", "x2"]).sort_values("x1")
met = g[g.tipo == "heurística"].set_index("familia")
exa = g[(g.tipo == "exata") & ~g.pareto_maximo]


def fronteira(ax, x_max, y_max):
    # trecho Pareto eficiente (contínuo) e extensões paralelas aos eixos, fracamente eficientes (tracejadas)
    ax.plot(ef.x1, ef.x2, color=AZUL, lw=1.6, zorder=2, solid_joinstyle="round")
    for xs, ys in (([ef.x1.iloc[0]] * 2, [y_max, ef.x2.iloc[0]]), ([ef.x1.iloc[-1], x_max], [ef.x2.iloc[-1]] * 2)):
        ax.plot(xs, ys, color=AZUL, lw=1.1, ls=(0, (4, 2)), zorder=2)


def pontos(ax):
    ax.scatter(exa.x1, exa.x2, s=22, facecolor="white", edgecolor=CINZA, lw=0.8, zorder=3)
    ax.scatter(ef.x1, ef.x2, s=30, color=AZUL, edgecolor="white", lw=0.8, zorder=4)
    ax.scatter(met.x1, met.x2, s=30, marker="s", color=LARANJA, edgecolor="white", lw=0.8, zorder=4)


def eixos(ax, titulo):
    ax.set_title(titulo, loc="left", fontsize=8)
    ax.set_xlabel("Pontos por mil pedidos cobertos (input 1/output)")
    ax.set_ylabel("Distância máxima por mil pedidos (km; input 2/output)")
    ax.xaxis.set_major_formatter(virgula)
    ax.yaxis.set_major_formatter(virgula)
    ax.grid(color="#e6e5e0", lw=0.5)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)


fig, (a, b) = plt.subplots(1, 2, figsize=(6.3, 3.0), gridspec_kw={"width_ratios": [1, 1.15]})

# (a) visão geral: todas as DMUs do grupo
fronteira(a, 6.3, 4.6)
pontos(a)
nomes = {"K-Means": (0.0, -0.14, "center"), "Ward": (0.05, 0.12, "left"), "MCLP": (0.08, 0.0, "left"),
         "p-mediana": (0.0, 0.14, "center"), "Complete": (0.0, 0.17, "center"), "Average": (0.0, 0.17, "center")}
for n, (dx, dy, al) in nomes.items():
    a.annotate(n, (met.x1[n] + dx, met.x2[n] + dy), ha=al, va="top" if dy < 0 else "bottom", fontsize=7, color=TINTA)
a.set_xlim(3.0, 6.3)
a.set_ylim(0.0, 4.6)
eixos(a, "(a) Todas as DMUs do grupo (R = 5 km)")

# (b) zoom: projeções do Complete e do Average
fronteira(b, 5.85, 1.2)
pontos(b)
c, av = met.loc["Complete"], met.loc["Average"]
h_c, h_a = c.ccr_maximo, av.ccr_maximo
bm = ef.iloc[-1]                                      # benchmark do Average: proximidade obrigatória, T = 6,6 km
alvo_c = (c.x1 * h_c, c.x2 * h_c)
radial_a = (av.x1 * h_a, av.x2 * h_a)
b.plot([c.x1, alvo_c[0]], [c.x2, alvo_c[1]], color=TINTA, lw=0.8, ls=(0, (3, 2)), zorder=1)
b.scatter(*alvo_c, s=26, facecolor="white", edgecolor=TINTA, lw=1.0, zorder=5)
b.annotate("", xy=radial_a, xytext=(av.x1, av.x2), arrowprops=dict(arrowstyle="-|>", lw=0.8, color=TINTA))
b.annotate("", xy=(bm.x1 + 0.02, bm.x2), xytext=radial_a,
           arrowprops=dict(arrowstyle="-|>", lw=0.8, color=TINTA, ls=(0, (3, 2))))
b.annotate(f"Complete\n$h_o^*$ = {h_c:.3f}".replace(".", ","), (c.x1, c.x2), xytext=(c.x1 + 0.12, c.x2 + 0.05),
           fontsize=7, va="bottom")
b.annotate("alvo do Complete\n(redução equiproporcional)", alvo_c, xytext=(4.30, 0.70), fontsize=7, ha="left",
           va="top", arrowprops=dict(arrowstyle="-", lw=0.5, color=TINTA, shrinkB=4))
b.annotate(f"Average\n$h_o^*$ = {h_a:.3f}".replace(".", ","), (av.x1, av.x2), xytext=(av.x1 - 0.02, av.x2 + 0.06),
           fontsize=7, ha="center", va="bottom")
folga = av.K * h_a - bm.K * (av.cob / bm.cob)
b.annotate(f"folga: {folga:.1f} pontos".replace(".", ","), ((radial_a[0] + bm.x1) / 2, bm.x2), xytext=(0, -9),
           textcoords="offset points", fontsize=7, ha="center", va="top")
b.annotate("T = 8 km (J828)", (ef.x1.iloc[-2], ef.x2.iloc[-2]), xytext=(6, 5), textcoords="offset points",
           fontsize=7, ha="left", va="bottom", color=AZUL)
b.annotate("T = 6,6 km (J825)", (bm.x1, bm.x2), xytext=(4, 6), textcoords="offset points", fontsize=7, ha="left",
           va="bottom", color=AZUL)
b.set_xlim(4.1, 5.85)
b.xaxis.set_major_locator(MultipleLocator(0.2))
b.set_ylim(0.6, 1.05)
eixos(b, "(b) Detalhe: projeções na fronteira")
b.set_ylabel("")

leg = [Line2D([], [], color=AZUL, lw=1.6, marker="o", ms=4.5, mec="white", label="Fronteira (DMUs Pareto eficientes)"),
       Line2D([], [], color=AZUL, lw=1.1, ls=(0, (4, 2)), label="Extensão fracamente eficiente"),
       Line2D([], [], ls="", marker="o", ms=4.5, mfc="white", mec=CINZA, label="Demais redes exatas"),
       Line2D([], [], ls="", marker="s", ms=4.5, color=LARANJA, mec="white", label="Redes dos métodos"),
       Line2D([], [], ls="", marker="o", ms=4.5, mfc="white", mec=TINTA, label="Alvo")]
fig.legend(handles=leg, loc="lower center", ncol=3, frameon=False, fontsize=7, bbox_to_anchor=(0.5, -0.04))
fig.tight_layout(rect=(0, 0.10, 1, 1))
fig.savefig(sys.argv[2], dpi=400, bbox_inches="tight")
print("ok", sys.argv[2], f"folga Average = {folga:.2f} pontos")
