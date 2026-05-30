"""
02_run_experiments.py
=====================
Roda todas as 38 configurações experimentais comparando os 4 paradigmas:
  - Agglomerative (3 linkages: average, complete, ward)
  - DBSCAN (varredura de eps)
  - K-Means demand-weighted
  - P-Median (heurística Teitz-Bart)

Entrada: data/demanda_por_cep.csv (gerado por 01_prepare_data.py)
Saída:   data/results_full.csv

Execução: python 02_run_experiments.py  (a partir de scripts/)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from methods import (method_agglomerative, method_dbscan,
                      method_kmeans_weighted, method_pmedian_heuristic,
                      evaluate)

DATA = Path("../data")

def main():
    df = pd.read_csv(DATA / "demanda_por_cep.csv")
    print(f"Pontos de demanda: {len(df):,} | total de pedidos: {df['n_pedidos'].sum():,}")

    K_VALUES = [5, 10, 15, 20, 25, 30]
    EPS_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0]
    TOP_100 = df.nlargest(100, 'n_pedidos').index.values  # candidatos para P-Median

    results = []

    print("\n=== Agglomerative (average, complete, Ward) ===")
    for K in K_VALUES:
        for lk in ['average', 'complete', 'ward']:
            labels, centers, rt = method_agglomerative(df, n_clusters=K, linkage=lk)
            m = evaluate(df, labels, centers)
            m.update({'method': f'Agglomerative-{lk}', 'K_target': K, 'runtime_s': rt})
            results.append(m)
            print(f"  {lk:>8s} K={K:2d}: d_med={m['weighted_avg_distance_km']:5.2f} | "
                  f"cov5={m['coverage_5km_%']:5.1f}%")

    print("\n=== K-Means demand-weighted ===")
    for K in K_VALUES:
        labels, centers, rt = method_kmeans_weighted(df, n_clusters=K)
        m = evaluate(df, labels, centers)
        m.update({'method': 'KMeans-weighted', 'K_target': K, 'runtime_s': rt})
        results.append(m)
        print(f"  K={K:2d}: d_med={m['weighted_avg_distance_km']:5.2f} | "
              f"cov5={m['coverage_5km_%']:5.1f}%")

    print("\n=== P-Median (heurística Teitz-Bart, candidatos = top 100) ===")
    for K in K_VALUES:
        labels, centers, rt = method_pmedian_heuristic(df, p=K, candidates_idx=TOP_100)
        m = evaluate(df, labels, centers)
        m.update({'method': 'P-Median', 'K_target': K, 'runtime_s': rt})
        results.append(m)
        print(f"  p={K:2d}: d_med={m['weighted_avg_distance_km']:5.2f} | "
              f"cov5={m['coverage_5km_%']:5.1f}%")

    print("\n=== DBSCAN (varredura de eps) ===")
    for eps in EPS_VALUES:
        labels, centers, rt, noise = method_dbscan(df, eps_km=eps, min_samples=3)
        m = evaluate(df, labels, centers)
        m.update({'method': 'DBSCAN', 'K_target': None, 'eps_km': eps,
                  'n_noise': noise, 'runtime_s': rt})
        results.append(m)
        print(f"  eps={eps:.1f}: K={m['n_facilities']:3d} noise={noise:3d} | "
              f"cov5={m['coverage_5km_%']:5.1f}%")

    out = DATA / "results_full.csv"
    pd.DataFrame(results).to_csv(out, index=False)
    print(f"\nResultados salvos em {out} ({len(results)} configurações).")

if __name__ == "__main__":
    main()
