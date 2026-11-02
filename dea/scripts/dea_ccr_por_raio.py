"""Artigo DEA: monta as redes (DMUs) de cada raio a partir da versão fixa e688d15 e roda o CCR orientado a inputs.

Uma rede entra se cumpre a meta (>= 9.207 de 9.691 pedidos dentro de R). Ficam de fora a grade interna
(pontos de grade não são locais candidatos), a ordem de desempate invertida e a rodada de K = 300, que só mede o teto.
Especificações: média = (K, distância média) -> pedidos cobertos; máximo = (K, distância máxima) -> pedidos cobertos.
Uso (na raiz do repositório): python dea/scripts/dea_ccr_por_raio.py data dea/resultados/redes_e_eficiencias_ccr.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog

META = 9207


def ccr_in(X, Y):
    """CCR orientado a insumo: fase 1 (theta) + fase 2 (máxima soma de folgas). Retorna (theta, Pareto-eficiente, pares)."""
    n, m, s = X.shape[0], X.shape[1], Y.shape[1]
    out = []
    for o in range(n):
        A = [np.r_[-X[o, i], X[:, i]] for i in range(m)] + [np.r_[0.0, -Y[:, r]] for r in range(s)]
        b = [0.0] * m + [-Y[o, r] for r in range(s)]
        th = linprog(np.r_[1.0, np.zeros(n)], A_ub=np.array(A), b_ub=np.array(b),
                     bounds=[(None, None)] + [(0, None)] * n, method="highs").x[0]
        Aeq = [np.r_[X[:, i], np.eye(m)[i], np.zeros(s)] for i in range(m)] + \
              [np.r_[Y[:, r], np.zeros(m), -np.eye(s)[r]] for r in range(s)]
        beq = [th * X[o, i] for i in range(m)] + [Y[o, r] for r in range(s)]
        x = linprog(np.r_[np.zeros(n), -np.ones(m + s)], A_eq=np.array(Aeq), b_eq=np.array(beq),
                    bounds=[(0, None)] * (n + m + s), method="highs").x
        forte = th > 1 - 1e-6 and x[n:].max() < 1e-6 * max(1, Y.max())
        out.append((th, forte, [j for j in range(n) if x[j] > 1e-6 and j != o]))
    return out


def redes(base):
    nomes = {"KMeans-weighted": "K-Means", "Agglomerative-ward": "Ward", "Agglomerative-complete": "Complete",
             "Agglomerative-average": "Average", "P-Median": "p-mediana", "MCLP": "MCLP"}
    sel = pd.read_csv(base / "v22_verified/main/service_selection.csv")
    sel = sel[sel.status == "selected"]
    h = pd.DataFrame({"tipo": "heurística", "familia": sel.method.map(nomes),
                      "conjunto": np.where(sel.method.isin(["P-Median", "MCLP"]),
                                           np.where(sel.scope == "main", "J300", "J828"), "centros calculados"),
                      "T": np.nan, "R": sel.radius_km, "K": sel.K_selected, "media": sel.weighted_avg_distance_km,
                      "maximo": sel.max_distance_km, "cob": sel.covered_orders})
    ex = pd.read_csv(base / "v22_verified/exact/exact_results.csv")
    ex = ex[(ex.has_primal_solution == True) & ex.weighted_avg_distance_km.notna()
            & ~ex.candidate_set.str.contains("grid|reverse")]
    rot = {"maximal_cover": "MCLP", "pmedian": "p-mediana", "partial_cover": "PSC"}
    e = pd.DataFrame({"tipo": "exata", "familia": ex.problem.map(rot), "conjunto": ex.candidate_set,
                      "T": ex.mandatory_radius_km, "R": ex.radius_km, "K": ex.K, "media": ex.weighted_avg_distance_km,
                      "maximo": ex.max_distance_km, "cob": ex.covered_orders})
    pr = pd.read_csv(base / "v23_verified/profiles/solver_profiles.csv")
    p = pd.DataFrame({"tipo": "exata", "familia": "PSC", "conjunto": pr.candidate_set, "T": pr.mandatory_radius_km,
                      "R": pr.radius_km, "K": pr.K, "media": pr.weighted_avg_distance_km,
                      "maximo": pr.max_distance_km, "cob": pr.covered_orders})
    t = pd.concat([h, e, p])
    # a mesma rede pode aparecer em mais de uma fonte ou conjunto (mesmos K, distâncias e cobertura): fica uma vez só
    chave = ["tipo", "familia", "R", "K", "media", "maximo", "cob"]
    t["T"] = t["T"].fillna(-1)
    t = t.groupby(chave + ["T"], as_index=False).agg(conjunto=("conjunto", lambda x: "/".join(sorted(set(x)))))
    t["T"] = t["T"].where(t["T"] >= 0)
    # quando a heurística encontrou a mesma rede da solução exata, mantém-se a heurística
    t = t.sort_values("tipo", ascending=False).drop_duplicates(["R", "K", "media", "maximo", "cob"])
    return t[(t.cob >= META) & (t.K < 300)].sort_values(["R", "K", "familia"]).reset_index(drop=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    base, saida = Path(sys.argv[1]), Path(sys.argv[2])
    todas = redes(base)
    partes = []
    for R in (3, 5, 10):
        df = todas[todas.R == R].reset_index(drop=True)
        for spec in ("media", "maximo"):
            r = ccr_in(df[["K", spec]].to_numpy(float), df[["cob"]].to_numpy(float))
            df[f"ccr_{spec}"] = [t for t, _, _ in r]
            df[f"pareto_{spec}"] = [f for _, f, _ in r]
            df[f"pares_{spec}"] = [";".join(str(j) for j in q) for _, _, q in r]
        partes.append(df.rename_axis("id_no_raio").reset_index())
    out = pd.concat(partes)
    out.to_csv(saida, index=False, encoding="utf-8")
    print(out.groupby(["R", "tipo"]).size().unstack())
    print(out[out.tipo == "exata"].groupby(["R", "familia", "conjunto"]).agg(
        n=("K", "size"), K_min=("K", "min"), K_max=("K", "max"),
        T=("T", lambda x: ", ".join(f"{v:g}" for v in sorted(x.dropna())))).to_string())
    pd.set_option("display.width", 200)
    print(out[out.tipo == "heurística"][["R", "familia", "conjunto", "K", "media", "maximo", "cob"]].round(2).to_string(index=False))
