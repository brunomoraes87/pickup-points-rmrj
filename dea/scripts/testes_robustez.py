"""Testes de robustez do artigo DEA (Seções 4.5 e 5.3), a partir de dea/resultados/resultados_dea_completos.csv.

1. CCR orientado a inputs com o output de todas as redes fixado na meta (9.207 pedidos).
2. Segunda fase com objetivo normalizado (cada folga dividida pelo valor da DMU em análise); as colunas s1/s2_objetivo_normalizado guardam as folgas nas unidades originais (pontos e km), obtidas com esse objetivo.
3. Verificação exploratória adicional, NÃO incluída no artigo: FDH orientado a inputs (sem convexidade e sem
   escalonamento: cada DMU só é comparada com DMUs observadas que produzem pelo menos o mesmo output).
Tolerância para eficiência igual a 1: 1e-6. Solver: HiGHS via scipy.optimize.linprog.
Uso (na raiz do repositório): python dea/scripts/testes_robustez.py dea/resultados/resultados_dea_completos.csv dea/resultados/testes_robustez.csv
"""
import sys

import numpy as np
import pandas as pd
from scipy.optimize import linprog

META, TOL = 9207.0, 1e-6
d = pd.read_csv(sys.argv[1])
linhas = []
for (R, perfil), g in d.groupby(["R", "perfil"], sort=False):
    X = g[["K", "dist"]].to_numpy().T
    Y = g["cob"].to_numpy()
    n = X.shape[1]
    for j, (_, row) in enumerate(g.iterrows()):
        # 1. output fixo na meta: min h  s.a. X lam <= h x_o ; sum(lam) * META >= META
        A = np.vstack([np.c_[-X[:, j], X], np.r_[0.0, -np.ones(n)]])
        h_fixo = linprog(np.r_[1.0, np.zeros(n)], A_ub=A, b_ub=np.r_[0.0, 0.0, -1.0],
                         bounds=[(0, None)] * (n + 1), method="highs").x[0]
        # 2. segunda fase normalizada: max s1/x1o + s2/x2o + s+/yo, com h do CCR fixo
        c = -np.r_[np.zeros(n), 1 / X[0, j], 1 / X[1, j], 1 / Y[j]]
        Aeq = np.vstack([np.r_[X[0], 1, 0, 0], np.r_[X[1], 0, 1, 0], np.r_[Y, 0, 0, -1]])
        s = linprog(c, A_eq=Aeq, b_eq=np.r_[row.h * X[0, j], row.h * X[1, j], Y[j]],
                    bounds=[(0, None)] * (n + 3), method="highs").x[n:]
        # 3. FDH orientado a inputs
        dom = Y >= Y[j] - TOL
        h_fdh = np.min(np.max(X[:, dom] / X[:, [j]], axis=0))
        linhas.append(dict(R=R, perfil=perfil, tipo=row.tipo, familia=row.familia, dmu=row.dmu, h_ccr=row.h,
                           h_bcc=row.h_bcc, h_output_fixo=h_fixo, dif_output_fixo=h_fixo - row.h,
                           s1_objetivo_normalizado=s[0], s2_objetivo_normalizado=s[1], dif_s1=s[0] - row.s1, dif_s2=s[1] - row.s2,
                           h_fdh=h_fdh))
t = pd.DataFrame(linhas)
t.to_csv(sys.argv[2], index=False, encoding="utf-8-sig")
m = t[t.tipo != "exata"]
print("output fixo: dif. máx. (todas / métodos):", round(t.dif_output_fixo.abs().max(), 4),
      round(m.dif_output_fixo.abs().max(), 4), "| eficientes métodos CCR / fixo:",
      int((m.h_ccr > 1 - TOL).sum()), int((m.h_output_fixo > 1 - TOL).sum()))
print("folgas normalizadas: dif. máx.:", float(max(t.dif_s1.abs().max(), t.dif_s2.abs().max())))
print("métodos com h = 1 — CCR / BCC / FDH:", int((m.h_ccr > 1 - TOL).sum()), int((m.h_bcc > 1 - TOL).sum()),
      int((m.h_fdh > 1 - TOL).sum()))
