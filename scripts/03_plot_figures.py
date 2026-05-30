"""
03_plot_figures.py
==================
Gera as 5 figuras do artigo a partir dos dados processados e resultados.

Entrada:
  - data/demanda_por_cep.csv
  - data/results_full.csv

Saída em figures/:
  - 01_exploracao_demanda.png
  - 02_cobertura_vs_K.png
  - 03_distancia_vs_K.png
  - 04_mapas_K15.png
  - 05_tradeoff_cobertura.png

Execução: python 03_plot_figures.py  (a partir de scripts/)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from methods import (method_agglomerative, method_kmeans_weighted,
                      method_pmedian_heuristic)

DATA = Path("../data")
FIGS = Path("../figures")
FIGS.mkdir(parents=True, exist_ok=True)

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['figure.dpi'] = 130

COLORS = {
    'Agglomerative-ward':     '#1f77b4',
    'Agglomerative-complete': '#9467bd',
    'KMeans-weighted':        '#2ca02c',
    'P-Median':               '#d62728',
}
MARKERS = {
    'Agglomerative-ward':     'o',
    'Agglomerative-complete': 's',
    'KMeans-weighted':        '^',
    'P-Median':               'D',
}
METHODS = list(COLORS.keys())


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
    axes[1].set_yscale('log')
    axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGS / '01_exploracao_demanda.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig02_cobertura_vs_K(res):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, metric, title in zip(axes,
                                  ['coverage_3km_%','coverage_5km_%','coverage_10km_%'],
                                  ['Cobertura 3 km','Cobertura 5 km','Cobertura 10 km']):
        for m in METHODS:
            sub = res[res['method']==m].sort_values('K_target')
            ax.plot(sub['K_target'], sub[metric], '-',
                    color=COLORS[m], marker=MARKERS[m], label=m,
                    linewidth=2, markersize=7)
        dbs = res[res['method']=='DBSCAN'].sort_values('n_facilities')
        ax.plot(dbs['n_facilities'], dbs[metric], '--', color='gray',
                marker='x', label='DBSCAN', alpha=0.7)
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
    dbs = res[res['method']=='DBSCAN'].sort_values('n_facilities')
    ax.plot(dbs['n_facilities'], dbs['weighted_avg_distance_km'],
            '--', color='gray', marker='x', label='DBSCAN', alpha=0.7)
    ax.set(xlabel='Número de pontos de retirada (K)',
           ylabel='Distância média ponderada (km)',
           title='Distância média ponderada por demanda vs número de pontos')
    ax.grid(alpha=0.3); ax.legend()
    plt.tight_layout()
    plt.savefig(FIGS / '03_distancia_vs_K.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig04_mapas_K15(demanda):
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    TOP = demanda.nlargest(100, 'n_pedidos').index.values
    K = 15
    configs = [
        ('Agglomerative-ward',     lambda d: method_agglomerative(d, n_clusters=K, linkage='ward')[:2]),
        ('Agglomerative-complete', lambda d: method_agglomerative(d, n_clusters=K, linkage='complete')[:2]),
        ('KMeans-weighted',        lambda d: method_kmeans_weighted(d, n_clusters=K)[:2]),
        ('P-Median',               lambda d: method_pmedian_heuristic(d, p=K, candidates_idx=TOP)[:2]),
    ]
    for ax, (name, fn) in zip(axes.flat, configs):
        labels, centers = fn(demanda)
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
               title=f'{name} — K={K}')
        ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGS / '04_mapas_K15.png', dpi=130, bbox_inches='tight')
    plt.close()


def fig05_tradeoff(res):
    fig, ax = plt.subplots(figsize=(8.5, 6))
    for m in METHODS:
        sub = res[res['method']==m].sort_values('K_target')
        ax.plot(sub['coverage_3km_%'], sub['coverage_10km_%'],
                color=COLORS[m], marker=MARKERS[m], label=m,
                linewidth=2, markersize=9)
        for _, r in sub.iterrows():
            ax.annotate(f'K={int(r["K_target"])}',
                        (r['coverage_3km_%'], r['coverage_10km_%']),
                        fontsize=7, alpha=0.7, xytext=(3,3), textcoords='offset points')
    dbs = res[res['method']=='DBSCAN']
    ax.scatter(dbs['coverage_3km_%'], dbs['coverage_10km_%'],
               color='gray', marker='x', s=60, label='DBSCAN', alpha=0.6)
    ax.set(xlabel='Cobertura 3 km (%)', ylabel='Cobertura 10 km (%)',
           title='Trade-off cobertura curta vs longa')
    ax.grid(alpha=0.3); ax.legend()
    plt.tight_layout()
    plt.savefig(FIGS / '05_tradeoff_cobertura.png', dpi=130, bbox_inches='tight')
    plt.close()


def main():
    demanda = pd.read_csv(DATA / 'demanda_por_cep.csv')
    res = pd.read_csv(DATA / 'results_full.csv')
    print("Gerando Figura 1 (exploração)...");  fig01_exploracao(demanda)
    print("Gerando Figura 2 (cobertura vs K)..."); fig02_cobertura_vs_K(res)
    print("Gerando Figura 3 (distância vs K)..."); fig03_distancia_vs_K(res)
    print("Gerando Figura 4 (mapas K=15)..."); fig04_mapas_K15(demanda)
    print("Gerando Figura 5 (trade-off)..."); fig05_tradeoff(res)
    print(f"\nTodas as figuras salvas em {FIGS}/")

if __name__ == "__main__":
    main()
