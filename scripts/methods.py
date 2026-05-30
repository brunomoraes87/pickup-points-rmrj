"""
methods.py - Metodos comparados para localizacao de pontos de retirada (RMRJ).
1) Agglomerative Hierarchical Clustering
2) DBSCAN
3) K-Means demand-weighted (baseline)
4) P-Median exato (MILP via PuLP)
Distancias: Haversine (km).
"""
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
import time

EARTH_R_KM = 6371.0088


def haversine_pairwise(lats, lngs):
    lats = np.radians(np.asarray(lats)); lngs = np.radians(np.asarray(lngs))
    dlat = lats[:, None] - lats[None, :]; dlng = lngs[:, None] - lngs[None, :]
    a = np.sin(dlat/2)**2 + np.cos(lats)[:, None]*np.cos(lats)[None, :]*np.sin(dlng/2)**2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def haversine_to_centers(lats, lngs, c_lats, c_lngs):
    lats = np.radians(np.asarray(lats))[:, None]; lngs = np.radians(np.asarray(lngs))[:, None]
    c_lats = np.radians(np.asarray(c_lats))[None, :]; c_lngs = np.radians(np.asarray(c_lngs))[None, :]
    dlat = c_lats - lats; dlng = c_lngs - lngs
    a = np.sin(dlat/2)**2 + np.cos(lats)*np.cos(c_lats)*np.sin(dlng/2)**2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def weighted_centroid(lats, lngs, weights):
    w = np.asarray(weights, dtype=float); w = w / w.sum()
    return np.average(lats, weights=w), np.average(lngs, weights=w)


def method_agglomerative(df, n_clusters=None, distance_threshold=None,
                          linkage='average', weighted=True):
    """Ward usa euclidean nas coordenadas; outros linkages usam Haversine precomputada."""
    t0 = time.time()
    coords = df[['lat','lng']].values; weights = df['n_pedidos'].values
    if linkage == 'ward':
        model = AgglomerativeClustering(n_clusters=n_clusters,
                                         distance_threshold=distance_threshold,
                                         metric='euclidean', linkage='ward')
        labels = model.fit_predict(coords)
    else:
        D = haversine_pairwise(coords[:,0], coords[:,1])
        model = AgglomerativeClustering(n_clusters=n_clusters,
                                         distance_threshold=distance_threshold,
                                         metric='precomputed', linkage=linkage)
        labels = model.fit_predict(D)
    centers = []
    for c in np.unique(labels):
        mask = labels == c
        if weighted:
            lat_c, lng_c = weighted_centroid(coords[mask,0], coords[mask,1], weights[mask])
        else:
            lat_c, lng_c = coords[mask,0].mean(), coords[mask,1].mean()
        centers.append((lat_c, lng_c))
    return labels, np.array(centers), time.time()-t0


def method_dbscan(df, eps_km=2.0, min_samples=3, weighted=True):
    t0 = time.time()
    coords = df[['lat','lng']].values; weights = df['n_pedidos'].values
    D = haversine_pairwise(coords[:,0], coords[:,1])
    model = DBSCAN(eps=eps_km, min_samples=min_samples, metric='precomputed')
    labels = model.fit_predict(D)
    centers = []
    for c in np.unique(labels[labels >= 0]):
        mask = labels == c
        if weighted:
            lat_c, lng_c = weighted_centroid(coords[mask,0], coords[mask,1], weights[mask])
        else:
            lat_c, lng_c = coords[mask,0].mean(), coords[mask,1].mean()
        centers.append((lat_c, lng_c))
    centers = np.array(centers) if centers else np.empty((0,2))
    n_noise = int((labels == -1).sum())
    return labels, centers, time.time()-t0, n_noise


def method_kmeans_weighted(df, n_clusters):
    t0 = time.time()
    coords = df[['lat','lng']].values; weights = df['n_pedidos'].values.astype(float)
    model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = model.fit_predict(coords, sample_weight=weights)
    return labels, model.cluster_centers_, time.time()-t0


def method_pmedian(df, p, candidates_idx=None, time_limit=60):
    """
    P-median MILP. Para tratabilidade, candidates_idx restringe quais pontos podem ser facility.
    Demanda continua usando todos os pontos.
    """
    from pulp import (LpProblem, LpVariable, LpMinimize, lpSum, LpBinary,
                       PULP_CBC_CMD, LpStatusOptimal, value)
    t0 = time.time()
    coords = df[['lat','lng']].values; weights = df['n_pedidos'].values.astype(float)
    n = len(df)
    if candidates_idx is None:
        candidates_idx = np.arange(n)
    candidates_idx = np.asarray(candidates_idx)
    m = len(candidates_idx)
    D_full = haversine_pairwise(coords[:,0], coords[:,1])
    D = D_full[:, candidates_idx]
    prob = LpProblem("p_median", LpMinimize)
    y = {j: LpVariable(f"y_{j}", cat=LpBinary) for j in range(m)}
    x = {(i, j): LpVariable(f"x_{i}_{j}", cat=LpBinary) for i in range(n) for j in range(m)}
    prob += lpSum(weights[i] * D[i, j] * x[(i, j)] for i in range(n) for j in range(m))
    prob += lpSum(y[j] for j in range(m)) == p
    for i in range(n):
        prob += lpSum(x[(i, j)] for j in range(m)) == 1
    for i in range(n):
        for j in range(m):
            prob += x[(i, j)] <= y[j]
    solver = PULP_CBC_CMD(msg=False, timeLimit=time_limit)
    prob.solve(solver)
    opened = [j for j in range(m) if value(y[j]) > 0.5]
    centers = coords[candidates_idx[opened]]
    labels = np.full(n, -1)
    for i in range(n):
        for k, j in enumerate(opened):
            if value(x[(i, j)]) > 0.5:
                labels[i] = k; break
    status = "Optimal" if prob.status == LpStatusOptimal else f"Status={prob.status}"
    return labels, centers, time.time()-t0, status


def evaluate(df, labels, centers, coverage_radii_km=(3, 5, 10)):
    coords = df[['lat','lng']].values
    weights = df['n_pedidos'].values.astype(float); total = weights.sum()
    if len(centers) == 0:
        return {'n_facilities': 0, 'weighted_avg_distance_km': np.nan,
                'max_distance_km': np.nan, 'p95_distance_km': np.nan,
                **{f'coverage_{r}km_%': 0.0 for r in coverage_radii_km}}
    D = haversine_to_centers(coords[:,0], coords[:,1], centers[:,0], centers[:,1])
    min_d = D.min(axis=1)
    m = {'n_facilities': int(len(centers)),
         'weighted_avg_distance_km': float(np.average(min_d, weights=weights)),
         'max_distance_km': float(min_d.max()),
         'p95_distance_km': float(np.percentile(min_d, 95))}
    for r in coverage_radii_km:
        m[f'coverage_{r}km_%'] = float(weights[min_d <= r].sum() / total * 100)
    return m


def method_pmedian_heuristic(df, p, candidates_idx=None, max_iter=100):
    """
    P-median via heuristica de troca (Teitz & Bart, 1968).
    Constroi solucao gulosa e melhora por trocas locais.
    Significativamente mais rapida que MILP para n>500.
    """
    t0 = time.time()
    coords = df[['lat','lng']].values
    weights = df['n_pedidos'].values.astype(float)
    n = len(df)
    if candidates_idx is None:
        candidates_idx = np.arange(n)
    candidates_idx = np.asarray(candidates_idx)
    D_full = haversine_pairwise(coords[:,0], coords[:,1])
    D = D_full[:, candidates_idx]

    def obj(selected):
        min_d = D[:, selected].min(axis=1)
        return float(np.sum(weights * min_d))

    # Greedy construction
    selected = []
    available = list(range(len(candidates_idx)))
    for _ in range(p):
        best_j, best_val = None, np.inf
        for j in available:
            val = obj(selected + [j])
            if val < best_val:
                best_val, best_j = val, j
        selected.append(best_j); available.remove(best_j)

    # Local search (interchange)
    improved = True; it = 0
    while improved and it < max_iter:
        improved = False; it += 1
        for k, jin in enumerate(list(selected)):
            current_val = obj(selected)
            for jout in available:
                trial = selected.copy(); trial[k] = jout
                trial_val = obj(trial)
                if trial_val < current_val - 1e-9:
                    selected = trial
                    available.remove(jout); available.append(jin)
                    current_val = trial_val; improved = True; break

    centers = coords[candidates_idx[selected]]
    D_sel = D[:, selected]
    labels = D_sel.argmin(axis=1)
    return labels, centers, time.time()-t0
