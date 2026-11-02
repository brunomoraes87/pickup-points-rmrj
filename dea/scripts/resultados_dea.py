"""Resultados completos da DEA (CCR orientado a inputs, forma do envelope, duas fases) para todas as DMUs.
Para cada DMU e perfil: eficiência h*, classificação, benchmarks com λ*, folgas e alvos; também o BCC (Σλ = 1)
e a rodada de robustez só com as seis redes dos métodos.
Entrada: dea/resultados/redes_e_eficiencias_ccr.csv (gerado por dea_ccr_por_raio.py).
Saída: dea/resultados/resultados_dea_completos.csv
Uso (na raiz do repositório): python dea/scripts/resultados_dea.py dea/resultados/redes_e_eficiencias_ccr.csv dea/resultados/resultados_dea_completos.csv
"""
import sys

import numpy as np
import pandas as pd
from scipy.optimize import linprog

TOL = 1e-6


def envelope(X, Y, o, vrs=False):
    """Duas fases para a DMU o. Retorna h*, λ*, folgas dos inputs (s-) e do output (s+)."""
    n, m, s = X.shape[0], X.shape[1], Y.shape[1]
    A = [np.r_[-X[o, i], X[:, i]] for i in range(m)] + [np.r_[0.0, -Y[:, r]] for r in range(s)]
    b = [0.0] * m + [-Y[o, r] for r in range(s)]
    eq = dict(A_eq=[np.r_[0.0, np.ones(n)]], b_eq=[1.0]) if vrs else {}
    h = linprog(np.r_[1.0, np.zeros(n)], A_ub=A, b_ub=b, bounds=[(None, None)] + [(0, None)] * n,
                method="highs", **eq).x[0]
    Aeq = [np.r_[X[:, i], np.eye(m)[i], np.zeros(s)] for i in range(m)] + \
          [np.r_[Y[:, r], np.zeros(m), -np.eye(s)[r]] for r in range(s)]
    beq = [h * X[o, i] for i in range(m)] + [Y[o, r] for r in range(s)]
    if vrs:
        Aeq.append(np.r_[np.ones(n), np.zeros(m + s)])
        beq.append(1.0)
    x = linprog(np.r_[np.zeros(n), -np.ones(m + s)], A_eq=Aeq, b_eq=beq, bounds=[(0, None)] * (n + m + s),
                method="highs").x
    return h, x[:n], x[n:n + m], x[n + m:]


def nome(r):
    if r.tipo == "heurística":
        return r.familia
    rot = {"PSC": "Cobertura parcial", "MCLP": "MCLP exato", "p-mediana": "p-mediana exata"}[r.familia]
    if r.familia == "PSC" and pd.notna(r["T"]):
        rot = "Proximidade obrigatória"
    t = f", T = {r['T']:g} km".replace(".", ",") if pd.notna(r["T"]) else ""
    return f"{rot} ({r.conjunto}, K = {r.K:.0f}{t})"


d = pd.read_csv(sys.argv[1])
d["dmu"] = d.apply(nome, axis=1)
linhas = []
for R, g in d.groupby("R"):
    g = g.reset_index(drop=True)
    Y = g[["cob"]].to_numpy(float)
    for perfil in ("media", "maximo"):
        X = g[["K", perfil]].to_numpy(float)
        met = g.index[g.tipo == "heurística"].to_numpy()
        for o in range(len(g)):
            h, lam, sm, sp = envelope(X, Y, o)
            hb = envelope(X, Y, o, vrs=True)[0]
            hm = envelope(X[met], Y[met], int(np.where(met == o)[0][0]))[0] if o in met else np.nan
            bm = [(g.dmu[k], lam[k]) for k in range(len(g)) if lam[k] > TOL]
            classe = ("Pareto eficiente" if h > 1 - TOL and max(sm.max(), sp.max()) < 1e-4 else
                      "fracamente eficiente" if h > 1 - TOL else "ineficiente")
            linhas.append(dict(R=R, perfil=perfil, tipo=g.tipo[o], familia=g.familia[o], dmu=g.dmu[o],
                               K=g.K[o], dist=X[o, 1], cob=Y[o, 0], h=h, classe=classe,
                               benchmarks="; ".join(f"{a} ({v:.3f})" for a, v in bm),
                               soma_lambda=lam.sum(), s1=sm[0], s2=sm[1], s_out=sp[0],
                               alvo_K=h * X[o, 0] - sm[0], alvo_dist=h * X[o, 1] - sm[1], alvo_cob=Y[o, 0] + sp[0],
                               h_bcc=hb, h_so_metodos=hm))
res = pd.DataFrame(linhas)
res.to_csv(sys.argv[2], index=False, encoding="utf-8-sig")
print(res[res.tipo == "heurística"][["R", "perfil", "familia", "h", "classe", "s1", "s2", "h_bcc", "h_so_metodos",
                                     "benchmarks"]].to_string())
print("soma lambda (CCR):", res.soma_lambda.min().round(3), "a", res.soma_lambda.max().round(3))
print("eficientes com exatas:", (res[res.tipo == "heurística"].h > 1 - TOL).sum(), "de 36;",
      "só métodos:", (res[res.tipo == "heurística"].h_so_metodos > 1 - TOL).sum(), "de 36")
