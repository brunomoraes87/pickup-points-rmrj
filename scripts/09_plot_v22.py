"""Regenerate v22 scientific figures, curve diagnostics and municipal tables.

The administrative union is a geographic test, not a dry-land or street mask.
All curves are evaluated from fresh fit checkpoints, without interpolation in K.
"""
import argparse
import colorsys
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch
from matplotlib.path import Path as PlotPath
import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[1]
METHODS = ['KMeans-weighted', 'Agglomerative-ward', 'Agglomerative-complete',
           'Agglomerative-average', 'P-Median', 'MCLP']
NAMES = dict(zip(METHODS, ['K-Means', 'Ward', 'Complete', 'Average', 'P-mediana', 'MCLP GA']))
COLORS = dict(zip(METHODS, ['#20854b', '#2567ab', '#7652a2', '#805335', '#c72636', '#e07616']))
RADIUSES = (3, 5, 10)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})


def haversine(coords, centers):
    x, y = np.radians(coords), np.radians(centers)
    dlat = x[:, None, 0] - y[None, :, 0]
    dlon = x[:, None, 1] - y[None, :, 1]
    a = np.sin(dlat / 2) ** 2 + np.cos(x[:, None, 0]) * np.cos(y[None, :, 0]) * np.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def quantile(d, w, q):
    indices = np.argsort(d, kind='stable')
    return float(d[indices][np.searchsorted(np.cumsum(w[indices]), int(np.ceil(q * w.sum())), side='left')])


def row_metrics(d, w, radius):
    covered = int(w[d <= radius].sum())
    return dict(covered_orders=covered, outside_orders=int(w.sum())-covered,
                coverage_pct=100*covered/int(w.sum()),
                weighted_avg_distance_km=float(np.dot(w, d)/w.sum()),
                median_empirical_km=quantile(d, w, .5), p95_empirical_km=quantile(d, w, .95),
                p99_empirical_km=quantile(d, w, .99), max_distance_km=float(d.max()))


def nondominated(frame, objectives):
    values = frame[objectives].to_numpy(float)
    keep = np.ones(len(frame), dtype=bool)
    for i, value in enumerate(values):
        keep[i] = not np.any(np.all(values <= value, axis=1) & np.any(values < value, axis=1))
    return keep


def save(fig, destination):
    fig.savefig(destination, dpi=220, bbox_inches='tight', metadata={'Software': 'pickup-points-rmrj v22'})
    plt.close(fig)


def polygon_patch(polygon):
    vertices, codes = [], []
    for ring in [polygon.exterior, *polygon.interiors]:
        pts = list(ring.coords)
        vertices.extend(pts)
        codes.extend([PlotPath.MOVETO] + [PlotPath.LINETO] * (len(pts)-2) + [PlotPath.CLOSEPOLY])
    return PathPatch(PlotPath(vertices, codes), facecolor='#e7e6df', edgecolor='#aaa89f', lw=.4, zorder=0)


def map_base(ax, polygons):
    for polygon in polygons:
        ax.add_patch(polygon_patch(polygon))
    ax.set(xlim=(-44.15, -42.45), ylim=(-23.15, -22.15), xlabel='Longitude', ylabel='Latitude')
    ax.set_aspect(1/np.cos(np.radians(-22.7)))
    ax.set_xticks([-44, -43.5, -43, -42.5])
    # Haversine-length horizontal scale, valid locally at the annotated latitude.
    y, x, length_km = -23.085, -44.00, 20
    delta = np.degrees(2*np.arcsin(np.sin(length_km/(2*6371.0088))/np.cos(np.radians(y))))
    ax.plot([x, x+delta], [y, y], color='#333', lw=2)
    ax.text(x+delta/2, y+.025, f'{length_km} km', ha='center', fontsize=8)
    ax.tick_params(labelsize=8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=REPO/'data')
    parser.add_argument('--results-dir', type=Path, default=REPO/'data/v22_main')
    parser.add_argument('--figures-dir', type=Path, default=REPO/'figures/v22')
    args = parser.parse_args()
    out, figs = args.results_dir, args.figures_dir
    figs.mkdir(parents=True, exist_ok=True)
    demand = pd.read_csv(args.data_dir/'demanda_por_cep.csv', dtype={'customer_zip_code_prefix': str})
    prefix_column = 'customer_zip_code_prefix' if 'customer_zip_code_prefix' in demand else 'CEP'
    demand[prefix_column] = demand[prefix_column].astype(str).str.zfill(5)
    coords, weights = demand[['lat', 'lng']].to_numpy(), demand.n_pedidos.to_numpy(int)
    orders = pd.read_csv(args.data_dir/'pedidos_rmrj_geo.csv', dtype={'customer_zip_code_prefix': str})
    orders.customer_zip_code_prefix = orders.customer_zip_code_prefix.str.zfill(5)
    assert not orders.order_id.duplicated().any() and len(orders) == int(weights.sum())
    order_counts = pd.crosstab(orders.customer_zip_code_prefix, orders.city_norm).reindex(demand[prefix_column], fill_value=0).to_numpy(int)
    cities = sorted(orders.city_norm.unique())
    assert np.array_equal(order_counts.sum(axis=1), weights)
    denominators = order_counts.sum(axis=0)
    scope = json.loads((args.data_dir/'geography/scope.json').read_text(encoding='utf-8-sig'))
    geography = json.loads((args.data_dir/'geography/rj_municipios_ibge.geojson').read_text(encoding='utf-8-sig'))
    geometries = [shape(f['geometry']) for f in geography['features'] if str(f['properties']['codarea']) in scope['municipality_codes']]
    union = unary_union(geometries)
    polygons = [p for g in geometries for p in ([g] if g.geom_type == 'Polygon' else g.geoms)]
    selection = pd.read_csv(out/'service_selection.csv')
    assignments = pd.read_csv(out/'service_assignments.csv', dtype={'CEP': str})
    facilities = pd.read_csv(out/'service_facilities.csv')
    facilities['inside_municipal_union'] = [bool(union.covers(Point(lng, lat))) for lat, lng in facilities[['lat', 'lng']].to_numpy()]
    facilities.to_csv(out/'facility_geography_v22.csv', index=False)
    municipality_rows, summaries = [], []
    for _, selected in selection[selection.K_selected.notna()].iterrows():
        key = dict(scope=selected.scope, method=selected.method, radius_km=selected.radius_km,
                   K_selected=int(selected.K_selected))
        sub = assignments[(assignments.scope == selected.scope) & (assignments.method == selected.method) & (assignments.radius_km == selected.radius_km)].copy()
        sub.CEP = sub.CEP.str.zfill(5)
        distance_by_prefix = sub.set_index('CEP').distance_km.reindex(demand[prefix_column]).to_numpy()
        assert np.isfinite(distance_by_prefix).all()
        covered = order_counts[distance_by_prefix <= selected.radius_km].sum(axis=0)
        for city, total, n in zip(cities, denominators, covered):
            municipality_rows.append(dict(**key, city_norm=city, orders=int(total), orders_covered=int(n),
                                          orders_outside=int(total-n), coverage_pct=100*int(n)/int(total)))
        outside = int((denominators-covered).sum())
        rio = int((denominators-covered)[cities.index('rio de janeiro')])
        summary = dict(**key, N_orders=int(denominators.sum()), zero_coverage_municipalities=int((covered == 0).sum()),
                       below_80pct_municipalities=int((covered/denominators < .8).sum()),
                       outside_orders=outside, rio_outside_orders=rio, rio_share_outside_pct=100*rio/outside if outside else 0)
        zero = [f'{city} ({int(n)} pedidos)' for city, n, c in zip(cities, denominators, covered) if c == 0]
        summary['zero_municipalities_denominators'] = '; '.join(zero)
        summaries.append(summary)
    pd.DataFrame(municipality_rows).to_csv(out/'service_by_municipality_v22.csv', index=False)
    pd.DataFrame(summaries).to_csv(out/'municipal_summary_v22.csv', index=False)
    curve_rows = []
    for path in sorted((out/'checkpoints').glob('*.npz')):
        stem = path.stem
        if stem.endswith('_trajectory'):
            continue
        for method in METHODS[:-1]:
            token = f'_{method}_K'
            if token in stem:
                curve_scope, remainder = stem.split(token)
                k_text, seed_text = remainder.split('_seed')
                break
        else:
            continue
        seed, k = int(seed_text), int(k_text)
        if method == 'KMeans-weighted' and seed != 42:
            continue
        with np.load(path) as checkpoint:
            centers = checkpoint['centers']
        distances = haversine(coords, centers).min(axis=1)
        for radius in RADIUSES:
            covered_city = order_counts[distances <= radius].sum(axis=0)
            curve_rows.append(dict(scope=curve_scope, method=method, radius_km=radius, K=k, seed=seed,
                                   comparison_space='continuous' if method != 'P-Median' else ('J300' if curve_scope == 'main' else 'J828'),
                                   zero_coverage_municipalities=int((covered_city == 0).sum()),
                                   **row_metrics(distances, weights, radius)))
    for path in sorted((out/'checkpoints').glob('*_trajectory.npz')):
        curve_scope, radius_text = path.stem.split('_MCLP_R')
        radius = float(radius_text.removesuffix('_trajectory'))
        with np.load(path) as checkpoint:
            chosen = checkpoint['chosen']
        for k in range(1, len(chosen)+1):
            distances = haversine(coords, coords[chosen[:k]]).min(axis=1)
            covered_city = order_counts[distances <= radius].sum(axis=0)
            curve_rows.append(dict(scope=curve_scope, method='MCLP', radius_km=radius, K=k, seed=-1,
                                   comparison_space='J300' if curve_scope == 'main' else 'J828',
                                   zero_coverage_municipalities=int((covered_city == 0).sum()),
                                   **row_metrics(distances, weights, radius)))
    curves = pd.DataFrame(curve_rows).sort_values(['scope', 'method', 'radius_km', 'K']).reset_index(drop=True)
    curves['eligible_95pct'] = curves.covered_orders >= int(np.ceil(.95*weights.sum()))
    for metric in ['weighted_avg_distance_km', 'p99_empirical_km', 'max_distance_km', 'zero_coverage_municipalities']:
        column = 'pareto_K_' + metric
        curves[column] = False
        for _, group in curves[curves.eligible_95pct].groupby(['radius_km', 'comparison_space']):
            curves.loc[group.index, column] = nondominated(group, ['K', metric])
    curves.to_csv(out/'frontier_curves_v22.csv', index=False)
    # Figure 1: method-specific selected network sizes, discrete sensitivity explicit.
    fig, ax = plt.subplots(figsize=(10, 6))
    chart = [('main', m) for m in METHODS] + [('all_candidates_sensitivity', m) for m in ['P-Median', 'MCLP']]
    radius_colors = {3: '#2f6ea3', 5: '#3c926b', 10: '#d4a13c'}
    for y, (curve_scope, method) in enumerate(chart):
        for radius, offset in zip(RADIUSES, [-.23, 0, .23]):
            rows = selection[(selection.scope == curve_scope) & (selection.method == method) & (selection.radius_km == radius)]
            if rows.empty:
                continue
            row = rows.iloc[0]
            if pd.isna(row.K_selected):
                ax.text(1, y+offset, 'teto abaixo de 95%', va='center', color='#a22', fontsize=9)
            else:
                k = int(row.K_selected)
                ax.barh(y+offset, k, height=.2, color=radius_colors[radius], hatch='///' if curve_scope != 'main' else None)
                ax.text(k+.8, y+offset, str(k), va='center')
    labels = [NAMES[m] + (' | J300' if m in ('P-Median', 'MCLP') and s == 'main' else '') + (' | J828, sens.' if s != 'main' else '') for s, m in chart]
    ax.set(yticks=range(len(labels)), yticklabels=labels, xlabel='K: instalações selecionadas', xlim=(0, 118))
    ax.invert_yaxis(); ax.grid(axis='x', alpha=.2); ax.set_axisbelow(True)
    fig.legend(handles=[Line2D([0], [0], color=radius_colors[r], lw=7, label=f'R={r} km') for r in RADIUSES], loc='lower center', ncol=3)
    fig.suptitle('Primeiro K viável em cada implementação e condição de candidatos')
    fig.tight_layout(rect=(0, .07, 1, .96)); save(fig, figs/'10_instalacoes_por_raio.png')
    # Figure 2: counts and tails together; no tautological selected-P95 panel.
    metrics = [('weighted_avg_distance_km', 'Média ponderada (km)'), ('p99_empirical_km', 'P99 empírico (km)'),
               ('max_distance_km', 'Distância máxima (km)'), ('zero_coverage_municipalities', 'Municípios com 0% de cobertura')]
    for radius in RADIUSES:
        fig, axes = plt.subplots(2, 2, figsize=(11, 8))
        subset = curves[curves.radius_km == radius]
        for ax, (metric, label) in zip(axes.flat, metrics):
            for (curve_scope, method), group in subset.groupby(['scope', 'method']):
                name = NAMES[method] + (' (J828 sens.)' if curve_scope != 'main' else (' (J300)' if method in ['P-Median', 'MCLP'] else ''))
                selected = selection[(selection.scope == curve_scope) & (selection.method == method) & (selection.radius_km == radius) & selection.K_selected.notna()]
                name += f' | K*={int(selected.iloc[0].K_selected)}' if not selected.empty else ' | sem K viável'
                group = group.sort_values('K')
                ax.plot(group.K, group[metric], color=COLORS[method], lw=1.1,
                        ls='--' if curve_scope != 'main' else '-', alpha=.72, label=name)
                frontier = group[group['pareto_K_'+metric]]
                ax.scatter(frontier.K, frontier[metric], s=12, color=COLORS[method], zorder=3)
                if not selected.empty:
                    k = int(selected.iloc[0].K_selected)
                    point = group[group.K == k].iloc[0]
                    ax.scatter([k], [point[metric]], marker='D', s=30, edgecolors='black', lw=.4, color=COLORS[method], zorder=4)
            ax.set(xlabel='K: instalações', ylabel=label); ax.grid(alpha=.18)
        handles, labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc='lower center', ncol=3, fontsize=8)
        fig.suptitle(f'R={radius} km | curvas calculadas, sem extrapolação em K\nLosango e K*: seleção; pontos: não dominância observada dentro de cada espaço de candidatos')
        fig.tight_layout(rect=(0, .10, 1, .90)); save(fig, figs/f'11_fronteiras_R{radius}.png')
    chosen_profiles = []
    for method in METHODS:
        chosen = selection[(selection.scope == 'main') & (selection.method == method) & (selection.radius_km == 3) & selection.K_selected.notna()]
        if chosen.empty:
            chosen = selection[(selection.scope == 'all_candidates_sensitivity') & (selection.method == method) & (selection.radius_km == 3) & selection.K_selected.notna()]
        if not chosen.empty:
            chosen_profiles.append(chosen.iloc[0])
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    labels = [NAMES[r.method]+f' | K={int(r.K_selected)}'+(' | J828 sens.' if r.scope != 'main' else '') for r in chosen_profiles]
    for ax, (metric, label) in zip(axes.flat, [('K_selected', 'Instalações (K)'), *metrics[:3]]):
        ax.barh(range(len(labels)), [r[metric] for r in chosen_profiles], color=[COLORS[r.method] for r in chosen_profiles])
        ax.set(yticks=range(len(labels)), yticklabels=labels, xlabel=label)
        ax.invert_yaxis(); ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('Redes selecionadas para R=3 km | quantidade, média e cauda\nComparações condicionais: J828 dos modelos discretos é uma sensibilidade separada')
    fig.tight_layout(rect=(0, 0, 1, .90)); save(fig, figs/'11_perfis_selecionados_R3.png')
    extremes = []
    for radius in RADIUSES:
        fig, axes = plt.subplots(3, 2, figsize=(11, 12))
        for ax, method in zip(axes.flat, METHODS):
            map_base(ax, polygons)
            rows = selection[(selection.scope == 'main') & (selection.method == method) & (selection.radius_km == radius) & selection.K_selected.notna()]
            if rows.empty:
                rows = selection[(selection.scope == 'all_candidates_sensitivity') & (selection.method == method) & (selection.radius_km == radius) & selection.K_selected.notna()]
            if rows.empty:
                ax.set_title(NAMES[method] + ': condição inviável'); continue
            row = rows.iloc[0]
            sub = assignments[(assignments.scope == row.scope) & (assignments.method == method) & (assignments.radius_km == radius)]
            cent = facilities[(facilities.scope == row.scope) & (facilities.method == method) & (facilities.radius_km == radius)]
            palette = np.array([colorsys.hsv_to_rgb((i*.61803398875)%1, .60, .74) for i in range(len(cent))])
            nearest, within = sub.nearest_facility.to_numpy(int), sub.distance_km.to_numpy() <= radius
            sizes = np.sqrt(sub.n_pedidos.to_numpy())*2+2
            ax.scatter(sub.lng, sub.lat, s=sizes, c=palette[nearest], alpha=.8, lw=0, zorder=2)
            ax.scatter(sub.loc[~within, 'lng'], sub.loc[~within, 'lat'], s=sizes[~within]+7, facecolors='none', edgecolors='#c02131', lw=.7, zorder=3)
            inside = cent.inside_municipal_union.to_numpy(bool)
            ax.scatter(cent.loc[inside, 'lng'], cent.loc[inside, 'lat'], s=18, marker='x', color='#151515', lw=.7, zorder=4)
            ax.scatter(cent.loc[~inside, 'lng'], cent.loc[~inside, 'lat'], s=60, marker='X', facecolors='#da202d', edgecolors='black', lw=.4, zorder=5)
            for _, point in sub.nlargest(3, 'distance_km').iterrows():
                fc = cent[cent.facility_id == int(point.nearest_facility)].iloc[0]
                ax.plot([point.lng, fc.lng], [point.lat, fc.lat], color='#c02131', lw=.8, zorder=3)
                extremes.append(dict(scope=row.scope, method=method, radius_km=radius, K=int(row.K_selected),
                                     CEP=point.CEP, orders=int(point.n_pedidos), distance_km=float(point.distance_km),
                                     facility_id=int(fc.facility_id), lat=float(point.lat), lng=float(point.lng),
                                     facility_lat=float(fc.lat), facility_lng=float(fc.lng)))
            suffix = ' | J828 sens.' if row.scope != 'main' else (' | J300' if method in ['P-Median', 'MCLP'] else '')
            ax.set_title(f'{NAMES[method]} | K={int(row.K_selected)}{suffix}\nCentroides de prefixo: {row.coverage_pct:.2f}%; fora: {int(row.outside_orders)} pedidos', fontsize=9)
        handles = [Line2D([], [], marker='x', color='#151515', ls='', label='Instalação proposta'),
                   Line2D([], [], marker='X', color='#da202d', ls='', label='Instalação fora da união municipal'),
                   Line2D([], [], marker='o', markerfacecolor='none', color='#c02131', ls='', label='Centroide além de R'),
                   Line2D([], [], color='#c02131', lw=.8, label='Três maiores distâncias')]
        fig.legend(handles=handles, loc='lower center', ncol=2, fontsize=9)
        fig.suptitle(f'Redes selecionadas | R={radius} km\nSombreado: polígonos municipais IBGE; máscara não certifica terra seca nem acesso viário', fontsize=12)
        fig.subplots_adjust(top=.90, bottom=.08, hspace=.55, wspace=.28)
        save(fig, figs/f'12_mapas_selecao_R{radius}.png')
    pd.DataFrame(extremes).to_csv(out/'figure_map_extremes_v22.csv', index=False)
    # Native-vs-nearest comparison preserves formations; P95 does not trim them.
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    native_examples = []
    for pair, method in enumerate(METHODS[:2]):
        row = selection[(selection.scope == 'main') & (selection.method == method) & (selection.radius_km == 3)].iloc[0]
        sub = assignments[(assignments.scope == row.scope) & (assignments.method == method) & (assignments.radius_km == 3)]
        cent = facilities[(facilities.scope == row.scope) & (facilities.method == method) & (facilities.radius_km == 3)]
        palette = np.array([colorsys.hsv_to_rgb((i*.61803398875)%1, .60, .74) for i in range(len(cent))])
        changed = sub[sub.native_label != sub.nearest_facility].copy()
        changed['reduction_km'] = changed.native_distance_km-changed.distance_km
        chosen = changed.nlargest(3, 'reduction_km')
        for ax, column, label in zip(axes[pair], ['native_label', 'nearest_facility'], ['Grupos de formação', 'Instalação mais próxima']):
            map_base(ax, polygons)
            ax.scatter(sub.lng, sub.lat, s=np.sqrt(sub.n_pedidos)*2+2, c=palette[sub[column].to_numpy(int)], lw=0, alpha=.8)
            ax.scatter(cent.lng, cent.lat, marker='x', s=16, c='#151515', lw=.7)
            for _, point in chosen.iterrows():
                fc = cent[cent.facility_id == int(point[column])].iloc[0]
                ax.plot([point.lng, fc.lng], [point.lat, fc.lat], c='#c02131', lw=1)
                if column == 'native_label':
                    native_examples.append(dict(method=method, K=int(row.K_selected), CEP=point.CEP,
                                                native_distance_km=float(point.native_distance_km),
                                                nearest_distance_km=float(point.distance_km), reduction_km=float(point.reduction_km)))
            ax.set_title(f'{NAMES[method]} | K={int(row.K_selected)} | {label}', fontsize=10)
    fig.suptitle('Atribuição nativa e avaliação pela instalação mais próxima\nP95 seleciona redes; nenhum prefixo é eliminado por distância')
    fig.tight_layout(rect=(0, 0, 1, .91)); save(fig, figs/'13_grupos_nativos_vs_proximidade_R3.png')
    pd.DataFrame(native_examples).to_csv(out/'figure_native_examples_v22.csv', index=False)
    manifest = {'source_hashes': {str(p.relative_to(args.data_dir)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.data_dir/'demanda_por_cep.csv', args.data_dir/'pedidos_rmrj_geo.csv']},
                'geometry_test': 'Administrative union; no claim of a dry-land, water or road mask',
                'figures': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(figs.glob('*.png'))},
                'curve_count': len(curves), 'map_extremes_count': len(extremes)}
    (figs/'figure_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'figures': len(manifest['figures']), 'curves': len(curves), 'municipal_summaries': len(summaries)}), flush=True)


if __name__ == '__main__':
    main()
