"""
03_plot_figures.py
==================
Gera as 8 figuras do artigo a partir dos dados processados e resultados:
  Figuras antigas (exploratórias e baseline):
    01 — Distribuição espacial e histograma de demanda
    02 — Cobertura efetiva vs K (raios 3, 5, 10 km)
    03 — Distância média ponderada vs K
    04_K15 — Mapas espaciais em K=15 (exploratório)
    05 — Trade-off cobertura curta vs longa
  Figuras do paper (v18):
    04_K70 — Mapas espaciais em K=70 (Figura 3 do paper)
    07_saturacao_K70 — Curvas de saturação que fundamentam K=70 (Figura 1)
    08_dominancia_linkages — Dominância intra-paradigma do Agglomerative (Figura 2)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from methods import (method_agglomerative, method_kmeans_weighted,
                      method_pmedian_heuristic, method_mclp_heuristic,
                      haversine_to_centers, evaluate)

DATA = Path("../data")
FIGS = Path("../figures")
FIGS.mkdir(parents=True, exist_ok=True)

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['figure.dpi'] = 130

COLORS = {
    'Agglomerative-ward':     '#1f77b4',
    'Agglomerative-complete': '#9467bd',
    'Agglomerative-average':  '#8c564b',
    'KMeans-weighted':        '#2ca02c',
    'P-Median':               '#d62728',
    'MCLP':                   '#ff7f0e',
}
MARKERS = {
    'Agglomerative-ward':     'o',
    'Agglomerative-complete': 's',
    'Agglomerative-average':  'v',
    'KMeans-weighted':        '^',
    'P-Median':               'D',
    'MCLP':                   'P',
}
METHODS = ['Agglomerative-ward', 'Agglomerative-complete', 'KMeans-weighted', 'P-Median']


def fig01_exploracao(demanda):
    fig, axes = plt.subplots(1, 2, figsize=(15, 7))
    axes[0].scatter(demanda['lng'], demanda['lat'],
                    s=np.sqrt(demanda['n_pedidos'])*4, alpha=0.5,
                    c=demanda['n_pedidos'], cmap='YlOrRd',
                    edgecolors='black', linewidth=0.3)
    axes[0].set(xlabel='Longitude', ylabel='Latitude',
                xlim=(-44.1, -42.5), ylim=(-23.1, -22.3),
                title='Distribuição espacial da demanda — RMRJ\n(tamanho/cor ∝ nº pedidos por CEP)')
    axes[0].grid(alpha=0.3)
    axes[1].hist(demanda['n_pedidos'], bins=50, color='steelblue', edgecolor='black')
    axes[1].set(xlabel='Nº pedidos por CEP', ylabel='Frequência (CEPs)',
                title='Distribuição de demanda por CEP')
    axes[1].set_yscale('log'); axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGS / '01_exploracao_demanda.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig02_cobertura_vs_K(res):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, metric, title, R in zip(axes,
                                     ['coverage_3km_%','coverage_5km_%','coverage_10km_%'],
                                     ['Cobertura 3 km','Cobertura 5 km','Cobertura 10 km'],
                                     [3, 5, 10]):
        for m in METHODS:
            sub = res[res['method']==m].sort_values('K_target')
            ax.plot(sub['K_target'], sub[metric], '-',
                    color=COLORS[m], marker=MARKERS[m], label=m,
                    linewidth=2, markersize=7)
        mclp = res[res['method']==f'MCLP-R{R}km'].sort_values('K_target')
        ax.plot(mclp['K_target'], mclp[metric], '-',
                color=COLORS['MCLP'], marker=MARKERS['MCLP'],
                label=f'MCLP (R={R}km, ótimo)', linewidth=2.5, markersize=9,
                markeredgecolor='black', markeredgewidth=0.5)
        dbs = res[res['method']=='DBSCAN'].sort_values('n_facilities')
        ax.plot(dbs['n_facilities'], dbs[metric], '--', color='gray',
                marker='x', label='DBSCAN', alpha=0.6)
        ax.set(xlabel='Número de pontos de retirada (K)',
               ylabel='% da demanda coberta', title=title, ylim=(0,105))
        ax.grid(alpha=0.3); ax.legend(fontsize=8, loc='lower right')
    plt.tight_layout()
    plt.savefig(FIGS / '02_cobertura_vs_K.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig03_distancia_vs_K(res):
    fig, ax = plt.subplots(figsize=(9, 5))
    for m in METHODS:
        sub = res[res['method']==m].sort_values('K_target')
        ax.plot(sub['K_target'], sub['weighted_avg_distance_km'],
                color=COLORS[m], marker=MARKERS[m], label=m,
                linewidth=2, markersize=7)
    mclp = res[res['method']=='MCLP-R5km'].sort_values('K_target')
    ax.plot(mclp['K_target'], mclp['weighted_avg_distance_km'],
            color=COLORS['MCLP'], marker=MARKERS['MCLP'],
            label='MCLP (R=5km)', linewidth=2, markersize=8,
            markeredgecolor='black', markeredgewidth=0.5)
    dbs = res[res['method']=='DBSCAN'].sort_values('n_facilities')
    ax.plot(dbs['n_facilities'], dbs['weighted_avg_distance_km'],
            '--', color='gray', marker='x', label='DBSCAN', alpha=0.6)
    ax.set(xlabel='Número de pontos de retirada (K)',
           ylabel='Distância média ponderada (km)',
           title='Distância média ponderada por demanda vs número de pontos')
    ax.grid(alpha=0.3); ax.legend()
    plt.tight_layout()
    plt.savefig(FIGS / '03_distancia_vs_K.png', dpi=130, bbox_inches='tight')
    plt.close()


def _plot_mapa_panel(ax, demanda, labels, centers, title):
    ax.scatter(demanda['lng'], demanda['lat'],
               s=np.sqrt(demanda['n_pedidos'])*3,
               c='lightgray', alpha=0.5, edgecolors='none')
    for c in np.unique(labels):
        mk = labels == c
        ax.scatter(demanda.loc[mk,'lng'], demanda.loc[mk,'lat'],
                   s=np.sqrt(demanda.loc[mk,'n_pedidos'])*3,
                   alpha=0.55, edgecolors='none')
    ax.scatter(centers[:,1], centers[:,0], s=180, marker='*',
               c='red', edgecolors='black', linewidths=1.5, zorder=5)
    ax.set(xlabel='Longitude', ylabel='Latitude',
           xlim=(-44.0, -42.5), ylim=(-23.1, -22.3),
           title=title)
    ax.grid(alpha=0.3)


def fig04_mapas_K15(demanda):
    """Mapas exploratórios em K=15."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    TOP = demanda.nlargest(100, 'n_pedidos').index.values
    K = 15
    configs = [
        ('Agglomerative-ward',     lambda d: method_agglomerative(d, n_clusters=K, linkage='ward')[:2]),
        ('Agglomerative-complete', lambda d: method_agglomerative(d, n_clusters=K, linkage='complete')[:2]),
        ('KMeans-weighted',        lambda d: method_kmeans_weighted(d, n_clusters=K)[:2]),
        ('P-Median',               lambda d: method_pmedian_heuristic(d, p=K, candidates_idx=TOP)[:2]),
        ('MCLP (R=3 km)',          lambda d: method_mclp_heuristic(d, p=K, radius_km=3, candidates_idx=TOP)[:2]),
        ('MCLP (R=5 km)',          lambda d: method_mclp_heuristic(d, p=K, radius_km=5, candidates_idx=TOP)[:2]),
    ]
    for ax, (name, fn) in zip(axes.flat, configs):
        labels, centers = fn(demanda)
        _plot_mapa_panel(ax, demanda, labels, centers, f'{name} — K={K}')
    plt.tight_layout()
    plt.savefig(FIGS / '04_mapas_K15.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig04_mapas_K70(demanda):
    """Mapas em K=70 (Figura 3 do paper) — configuração final analisada."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    TOP = demanda.nlargest(100, 'n_pedidos').index.values
    K = 70
    configs = [
        ('K-Means weighted',         lambda d: method_kmeans_weighted(d, n_clusters=K)[:2]),
        ('Agglomerative-Ward',       lambda d: method_agglomerative(d, n_clusters=K, linkage='ward')[:2]),
        ('Agglomerative-complete',   lambda d: method_agglomerative(d, n_clusters=K, linkage='complete')[:2]),
        ('Agglomerative-average',    lambda d: method_agglomerative(d, n_clusters=K, linkage='average')[:2]),
        ('P-Median',                 lambda d: method_pmedian_heuristic(d, p=K, candidates_idx=TOP)[:2]),
        ('MCLP (R=3 km)',            lambda d: method_mclp_heuristic(d, p=K, radius_km=3, candidates_idx=TOP)[:2]),
    ]
    for ax, (name, fn) in zip(axes.flat, configs):
        labels, centers = fn(demanda)
        _plot_mapa_panel(ax, demanda, labels, centers, f'{name} — K={K}')
    plt.tight_layout()
    plt.savefig(FIGS / '04_mapas_K70.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig05_tradeoff(res):
    fig, ax = plt.subplots(figsize=(9, 6))
    for m in METHODS:
        sub = res[res['method']==m].sort_values('K_target')
        ax.plot(sub['coverage_3km_%'], sub['coverage_10km_%'],
                color=COLORS[m], marker=MARKERS[m], label=m,
                linewidth=2, markersize=9)
        for _, r in sub.iterrows():
            ax.annotate(f'K={int(r["K_target"])}',
                        (r['coverage_3km_%'], r['coverage_10km_%']),
                        fontsize=7, alpha=0.6, xytext=(3,3), textcoords='offset points')
    mclp3 = res[res['method']=='MCLP-R3km'].sort_values('K_target')
    ax.plot(mclp3['coverage_3km_%'], mclp3['coverage_10km_%'],
            color=COLORS['MCLP'], marker=MARKERS['MCLP'],
            linestyle='-', label='MCLP (R=3km, ótimo cobertura curta)',
            linewidth=2.5, markersize=10, markeredgecolor='black', markeredgewidth=0.5)
    mclp10 = res[res['method']=='MCLP-R10km'].sort_values('K_target')
    ax.plot(mclp10['coverage_3km_%'], mclp10['coverage_10km_%'],
            color='#ffb87a', marker=MARKERS['MCLP'],
            linestyle='--', label='MCLP (R=10km, ótimo cobertura longa)',
            linewidth=2, markersize=10, markeredgecolor='black', markeredgewidth=0.5)
    dbs = res[res['method']=='DBSCAN']
    ax.scatter(dbs['coverage_3km_%'], dbs['coverage_10km_%'],
               color='gray', marker='x', s=60, label='DBSCAN', alpha=0.6)
    ax.set(xlabel='Cobertura 3 km (%)', ylabel='Cobertura 10 km (%)',
           title='Trade-off cobertura curta vs longa\n(linhas MCLP delimitam a fronteira de Pareto)')
    ax.grid(alpha=0.3); ax.legend(fontsize=8, loc='lower right')
    plt.tight_layout()
    plt.savefig(FIGS / '05_tradeoff_cobertura.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig07_saturacao_K70(demanda):
    """Figura 1 do paper — saturação das curvas em K=70."""
    TOP = demanda.nlargest(100, 'n_pedidos').index.values
    K_range = list(range(10, 161, 10))

    series = {
        'K-Means weighted':    ('#2ca02c', '^', []),
        'Agglomerative-Ward':  ('#1f77b4', 'o', []),
        'MCLP — R=3 km':       ('#ff7f0e', 'P', []),
    }
    series_dist = {k: ('#2ca02c', '^', []) if k == 'K-Means weighted'
                   else ('#1f77b4', 'o', []) if k == 'Agglomerative-Ward'
                   else ('#ff7f0e', 'P', []) for k in series}

    for K in K_range:
        _, c_kmeans, _ = method_kmeans_weighted(demanda, n_clusters=K)
        _, c_ward, _ = method_agglomerative(demanda, n_clusters=K, linkage='ward')
        _, c_mclp, _ = method_mclp_heuristic(demanda, p=K, radius_km=3, candidates_idx=TOP)
        coords = demanda[['lat','lng']].values
        weights = demanda['n_pedidos'].values.astype(float)
        total = weights.sum()
        for name, centers in [('K-Means weighted', c_kmeans),
                              ('Agglomerative-Ward', c_ward),
                              ('MCLP — R=3 km', c_mclp)]:
            D = haversine_to_centers(coords[:,0], coords[:,1], centers[:,0], centers[:,1])
            min_d = D.min(axis=1)
            cov_3 = float(weights[min_d <= 3].sum() / total * 100)
            dw = float(np.average(min_d, weights=weights))
            series[name][2].append(cov_3)
            series_dist[name][2].append(dw)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for name, (color, marker, vals) in series.items():
        axes[0].plot(K_range, vals, color=color, marker=marker,
                     label=name, linewidth=2, markersize=7)
    axes[0].axvline(70, color='red', linestyle='--', alpha=0.7, label='K=70')
    axes[0].set(xlabel='Número de pontos de retirada (K)',
                ylabel='Cobertura efetiva em 3 km (%)',
                title='Saturação da cobertura efetiva')
    axes[0].grid(alpha=0.3); axes[0].legend(fontsize=9)

    for name, (color, marker, vals) in series_dist.items():
        axes[1].plot(K_range, vals, color=color, marker=marker,
                     label=name, linewidth=2, markersize=7)
    axes[1].axvline(70, color='red', linestyle='--', alpha=0.7, label='K=70')
    axes[1].set(xlabel='Número de pontos de retirada (K)',
                ylabel='Distância média ponderada (km)',
                title='Estabilização da distância média')
    axes[1].grid(alpha=0.3); axes[1].legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(FIGS / '07_saturacao_K70.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig08_dominancia_linkages(demanda):
    """Figura 2 do paper — dominância intra-paradigma do Agglomerative em K=70."""
    K = 70
    coords = demanda[['lat','lng']].values
    weights = demanda['n_pedidos'].values.astype(float)
    total = weights.sum()

    metrics = {'d̄w (km)': [], 'Cobertura 3km (%)': [], 'P95 (km)': []}
    linkages = ['average', 'complete', 'ward']
    colors_lk = ['#d62728', '#9467bd', '#1f77b4']  # average vermelho destacando dominância
    for lk in linkages:
        _, centers, _ = method_agglomerative(demanda, n_clusters=K, linkage=lk)
        D = haversine_to_centers(coords[:,0], coords[:,1], centers[:,0], centers[:,1])
        min_d = D.min(axis=1)
        metrics['d̄w (km)'].append(float(np.average(min_d, weights=weights)))
        metrics['Cobertura 3km (%)'].append(float(weights[min_d <= 3].sum() / total * 100))
        metrics['P95 (km)'].append(float(np.percentile(min_d, 95)))

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, (metric, vals) in zip(axes, metrics.items()):
        bars = ax.bar(linkages, vals, color=colors_lk, edgecolor='black')
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x()+bar.get_width()/2, v, f'{v:.2f}',
                    ha='center', va='bottom', fontsize=10, fontweight='bold')
        ax.set_title(f'{metric} — Agglomerative em K={K}')
        ax.set_ylabel(metric)
        ax.grid(alpha=0.3, axis='y')
    plt.suptitle('Dominância intra-paradigma: average (vermelho) é dominado em todas as métricas',
                 fontsize=11, y=1.02)
    plt.tight_layout()
    plt.savefig(FIGS / '08_dominancia_linkages.png', dpi=130, bbox_inches='tight')
    plt.close()


def main():
    demanda = pd.read_csv(DATA / 'demanda_por_cep.csv')
    res = pd.read_csv(DATA / 'results_full.csv')

    print("Figura 01 — exploração...");        fig01_exploracao(demanda)
    print("Figura 02 — cobertura vs K...");    fig02_cobertura_vs_K(res)
    print("Figura 03 — distância vs K...");    fig03_distancia_vs_K(res)
    print("Figura 04 K=15 — mapas explor...");  fig04_mapas_K15(demanda)
    print("Figura 04 K=70 — mapas paper...");   fig04_mapas_K70(demanda)
    print("Figura 05 — trade-off...");          fig05_tradeoff(res)
    print("Figura 07 — saturação K=70...");     fig07_saturacao_K70(demanda)
    print("Figura 08 — dominância linkages..."); fig08_dominancia_linkages(demanda)
    print(f"\nTodas as figuras salvas em {FIGS}/")


if __name__ == "__main__":
    main()
