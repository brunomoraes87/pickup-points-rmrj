"""
02_run_experiments.py
=====================
Roda todas as configurações experimentais comparando 5 paradigmas:
  - Agglomerative (3 linkages: average, complete, ward)
  - DBSCAN (varredura de eps)
  - K-Means demand-weighted
  - P-Median (heurística Teitz-Bart) — minimiza distância média ponderada
  - MCLP (heurística gulosa) — maximiza cobertura em raio R (Church & ReVelle, 1974)

Entrada: data/demanda_por_cep.csv
Saída:   data/results_full.csv

Execução: python 02_run_experiments.py  (a partir de scripts/)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from methods import (method_agglomerative, method_dbscan,
                      method_kmeans_weighted, method_pmedian_heuristic,
                      method_mclp_heuristic, evaluate)

DATA = Path("../data")

def main():
    df = pd.read_csv(DATA / "demanda_por_cep.csv")
    print(f"Pontos de demanda: {len(df):,} | total de pedidos: {df['n_pedidos'].sum():,}")

    K_VALUES = [5, 10, 15, 20, 25, 30]
    EPS_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0]
    R_VALUES_MCLP = [3, 5, 10]
    TOP_100 = df.nlargest(100, 'n_pedidos').index.values

    results = []

    print("\n=== Agglomerative ===")
    for K in K_VALUES:
        for lk in ['average', 'complete', 'ward']:
            labels, centers, rt = method_agglomerative(df, n_clusters=K, linkage=lk)
            m = evaluate(df, labels, centers)
            m.update({'method': f'Agglomerative-{lk}', 'K_target': K, 'runtime_s': rt})
            results.append(m)

    print("=== K-Means demand-weighted ===")
    for K in K_VALUES:
        labels, centers, rt = method_kmeans_weighted(df, n_clusters=K)
        m = evaluate(df, labels, centers)
        m.update({'method': 'KMeans-weighted', 'K_target': K, 'runtime_s': rt})
        results.append(m)

    print("=== P-Median (Teitz-Bart) ===")
    for K in K_VALUES:
        labels, centers, rt = method_pmedian_heuristic(df, p=K, candidates_idx=TOP_100)
        m = evaluate(df, labels, centers)
        m.update({'method': 'P-Median', 'K_target': K, 'runtime_s': rt})
        results.append(m)

    print("=== MCLP (Church & ReVelle, 1974) ===")
    for R in R_VALUES_MCLP:
        for K in K_VALUES:
            labels, centers, rt = method_mclp_heuristic(df, p=K, radius_km=R, candidates_idx=TOP_100)
            m = evaluate(df, labels, centers)
            m.update({'method': f'MCLP-R{R}km', 'K_target': K, 'radius_km': R, 'runtime_s': rt})
            results.append(m)
            print(f"  R={R}km K={K:2d}: cov_{R}km={m[f'coverage_{R}km_%']:5.1f}% (objetivo)")

    print("=== DBSCAN ===")
    for eps in EPS_VALUES:
        labels, centers, rt, noise = method_dbscan(df, eps_km=eps, min_samples=3)
        m = evaluate(df, labels, centers)
        m.update({'method': 'DBSCAN', 'K_target': None, 'eps_km': eps,
                  'n_noise': noise, 'runtime_s': rt})
        results.append(m)

    out = DATA / "results_full.csv"
    pd.DataFrame(results).to_csv(out, index=False)
    print(f"\nResultados salvos em {out} ({len(results)} configuracoes).")

if __name__ == "__main__":
    main()
