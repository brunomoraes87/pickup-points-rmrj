"""
Exemplo de uso: roda os quatro métodos comparados e gera tabela K=20.
"""
import sys, pandas as pd
sys.path.insert(0, '../scripts')

from methods import (method_agglomerative, method_dbscan,
                      method_kmeans_weighted, method_pmedian_heuristic,
                      evaluate)

df = pd.read_csv('../data/demanda_por_cep.csv')
print(f"Pontos de demanda: {len(df)}, total de pedidos: {df['n_pedidos'].sum()}")

K = 20
TOP = df.nlargest(100, 'n_pedidos').index.values

results = []
for lk in ['average', 'complete', 'ward']:
    labels, centers, _ = method_agglomerative(df, n_clusters=K, linkage=lk)
    m = evaluate(df, labels, centers); m['method'] = f'Agglomerative-{lk}'
    results.append(m)

labels, centers, _ = method_kmeans_weighted(df, n_clusters=K)
m = evaluate(df, labels, centers); m['method'] = 'KMeans-weighted'
results.append(m)

labels, centers, _ = method_pmedian_heuristic(df, p=K, candidates_idx=TOP)
m = evaluate(df, labels, centers); m['method'] = 'P-Median'
results.append(m)

cols = ['method','weighted_avg_distance_km','coverage_3km_%','coverage_5km_%','coverage_10km_%']
print(pd.DataFrame(results)[cols].to_string(index=False))
