"""
Exemplo de uso: roda os cinco paradigmas comparados no paper em K=70
e imprime a tabela de comparação apples-to-apples (Tabela 1 do paper).
"""
import sys, pandas as pd
sys.path.insert(0, '../scripts')

from methods import (method_agglomerative, method_kmeans_weighted,
                      method_pmedian_heuristic, method_mclp_heuristic,
                      evaluate)

df = pd.read_csv('../data/demanda_por_cep.csv')
print(f"Pontos de demanda: {len(df)}, total de pedidos: {df['n_pedidos'].sum()}")

K = 70
TOP = df.nlargest(100, 'n_pedidos').index.values

results = []

# Agglomerative — 3 linkages
for lk in ['average', 'complete', 'ward']:
    labels, centers, _ = method_agglomerative(df, n_clusters=K, linkage=lk)
    m = evaluate(df, labels, centers); m['method'] = f'Agglomerative-{lk}'
    results.append(m)

# K-Means demand-weighted
labels, centers, _ = method_kmeans_weighted(df, n_clusters=K)
m = evaluate(df, labels, centers); m['method'] = 'KMeans-weighted'
results.append(m)

# P-Median (heurística Teitz-Bart)
labels, centers, _ = method_pmedian_heuristic(df, p=K, candidates_idx=TOP)
m = evaluate(df, labels, centers); m['method'] = 'P-Median'
results.append(m)

# MCLP — R = 3 km (configuração do paper)
labels, centers, _ = method_mclp_heuristic(df, p=K, radius_km=3, candidates_idx=TOP)
m = evaluate(df, labels, centers); m['method'] = 'MCLP-R3km'
results.append(m)

cols = ['method', 'weighted_avg_distance_km', 'max_distance_km',
        'p95_distance_km', 'coverage_3km_%', 'coverage_5km_%', 'coverage_10km_%']
out = pd.DataFrame(results)[cols].round({'weighted_avg_distance_km': 2,
                                          'max_distance_km': 2,
                                          'p95_distance_km': 2,
                                          'coverage_3km_%': 1,
                                          'coverage_5km_%': 1,
                                          'coverage_10km_%': 1})
print("\nComparação em K=70 (Tabela 1 do paper):\n")
print(out.to_string(index=False))
