"""Generate manuscript numbers and their provenance from completed v22 outputs."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=REPO/'data')
    parser.add_argument('--main-dir', type=Path, default=REPO/'data/v22_main')
    parser.add_argument('--exact-dir', type=Path, default=REPO/'data/v22_exact')
    parser.add_argument('--sensitivity-dir', type=Path, default=REPO/'data/v22_sensitivity')
    parser.add_argument('--out', type=Path, default=REPO/'data/paper_values_v22.json')
    args = parser.parse_args()
    values, sources = {}, {}

    def add(key, value, path, column, selection=None, aggregation='identity', category='scientific_result'):
        path = path.resolve()
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and not np.isfinite(value):
            return
        if isinstance(value, bool):
            return
        if not isinstance(value, (int, float)):
            return
        values[key] = dict(value=value, file=str(path), column=column, filter=selection or {},
                           aggregation=aggregation, category=category)
        if str(path) not in sources:
            sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()

    def table(prefix, path, tag_columns):
        frame = pd.read_csv(path)
        for _, row in frame.iterrows():
            tags = {column: (row[column].item() if isinstance(row[column], np.generic) else row[column]) for column in tag_columns}
            key = '.'.join(str(int(v)) if isinstance(v, (float, int)) and np.isfinite(v) and v == int(v) else str(v) for v in tags.values())
            for column in frame.select_dtypes(include='number').columns:
                add(f'{prefix}.{key}.{column}', row[column], path, column, tags)
        return frame

    metadata_path = args.main_dir/'service_metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    if metadata['run_state'] != 'complete':
        raise ValueError('Main search is incomplete')
    for field in ['total_orders', 'required_orders', 'n_demand_points', 'earth_radius_km']:
        add('data.'+field, metadata[field], metadata_path, field)
    for i, value in enumerate(metadata['protocol']['radii_km']):
        add(f'protocol.radius.{i}', value, metadata_path, f'protocol.radii_km[{i}]', category='protocol')
    for i, value in enumerate(metadata['protocol']['seeds']):
        add(f'protocol.seed.{i}', value, metadata_path, f'protocol.seeds[{i}]', category='protocol')
    add('protocol.n_seeds', len(metadata['protocol']['seeds']), metadata_path, 'protocol.seeds', aggregation='length', category='protocol')
    add('protocol.candidates', len(metadata['protocol']['candidate_indices']), metadata_path, 'protocol.candidate_indices', aggregation='length', category='protocol')
    add('protocol.target_pct', 100*19/20, metadata_path, 'protocol.target', aggregation='parse rational × 100', category='protocol')
    for field in ['n_init', 'pmedian_max_iter', 'max_k']:
        add('protocol.'+field, metadata['protocol'][field], metadata_path, 'protocol.'+field, category='protocol')
    for field in ['max_iter', 'tol']:
        add('protocol.kmeans.'+field, metadata['protocol']['kmeans_parameters'][field], metadata_path, 'protocol.kmeans_parameters.'+field, category='protocol')
    orders_path = args.data_dir/'pedidos_rmrj_geo.csv'
    orders = pd.read_csv(orders_path)
    years = pd.to_datetime(orders.order_purchase_timestamp).dt.year
    add('data.orders_year_min', int(years.min()), orders_path, 'order_purchase_timestamp', {}, 'min year')
    add('data.orders_year_max', int(years.max()), orders_path, 'order_purchase_timestamp', {}, 'max year')
    selected = table('main', args.main_dir/'service_selection.csv', ['scope', 'method', 'radius_km'])
    curves = table('curve', args.main_dir/'service_curves.csv', ['scope', 'method', 'radius_km', 'K_target', 'seed'])
    table('municipal', args.main_dir/'municipal_summary_v22.csv', ['scope', 'method', 'radius_km'])
    table('facility', args.main_dir/'facility_geography_v22.csv', ['scope', 'method', 'radius_km', 'facility_id'])
    table('exact', args.exact_dir/'exact_results.csv', ['job_id'])
    quality_path = args.data_dir/'quality/summary.json'
    quality = json.loads(quality_path.read_text(encoding='utf-8'))
    add('data.n_methods', selected[selected.scope == 'main'].method.nunique(), args.main_dir/'service_selection.csv', 'method', {'scope':'main'}, 'nunique')
    for field, value in quality.items():
        add('quality.'+field, value, quality_path, field)
    for field, value in quality['geo_validation'].items():
        add('quality.geo.'+field, value, quality_path, 'geo_validation.'+field)
    geography_path = args.data_dir/'geography/scope.json'
    geography = json.loads(geography_path.read_text(encoding='utf-8'))
    add('data.n_municipalities', len(geography['municipality_codes']), geography_path, 'municipality_codes', aggregation='length')
    add('data.geometry_year', geography['geometry_reference_year'], geography_path, 'geometry_reference_year', category='source_metadata')
    sensitivity_metadata = args.sensitivity_dir/'metadata.json'
    sens_metadata = json.loads(sensitivity_metadata.read_text(encoding='utf-8'))
    if not sens_metadata.get('complete'):
        raise ValueError('Sensitivities are incomplete or were run before code freeze')
    sens = table('sensitivity', args.sensitivity_dir/'sensitivity_selection.csv', ['case', 'method', 'radius_km'])
    robustness_cases = ['main', 'geodesic_eval_only', 'geodesic', 'median', 'dedup_full', 'projected_inverse', 'projected_partition_angular']
    for (method, radius), group in sens[sens['case'].isin(robustness_cases)].groupby(['method','radius_km']):
        finite = group.K_selected.dropna()
        if not finite.empty:
            for label, value in [('minimum',finite.min()),('maximum',finite.max()),('n_finite_variants',len(finite))]:
                add(f'robustness.{method}.{int(radius)}.{label}', float(value), args.sensitivity_dir/'sensitivity_selection.csv', 'K_selected', {'method':method,'radius_km':radius,'case_in':robustness_cases}, label)
    table('diagnostic', args.sensitivity_dir/'sensitivity_network_diagnostics.csv', ['case', 'method', 'radius_km'])
    table('seed30', args.sensitivity_dir/'seed30_by_K.csv', ['radius_km', 'K'])
    for name in ['main', 'D16', 'D22']:
        matches = sens[sens.cohort.astype(str).str.lower() == name.lower()]
        if matches.empty:
            continue
        for field in ['N_orders', 'N_prefixes', 'N_unique_buyers', 'required_orders']:
            assert matches[field].nunique() == 1, (name, field)
            add(f'cohort.{name}.{field}', int(matches.iloc[0][field]), args.sensitivity_dir/'sensitivity_selection.csv', field, {'cohort':name}, aggregation='unique value')
    path = args.sensitivity_dir/'prefix_dispersion.csv'
    dispersion = pd.read_csv(path)
    for threshold in [1, 3]:
        mask = dispersion.p90_record_to_mean_km > threshold
        add(f'dispersion.p90_gt{threshold}.prefixes', int(mask.sum()), path, 'p90_record_to_mean_km', {'gt':threshold}, 'count')
        n = int(dispersion.loc[mask, 'n_pedidos'].sum())
        add(f'dispersion.p90_gt{threshold}.orders', n, path, 'n_pedidos', {'p90_record_to_mean_km_gt':threshold}, 'sum')
        add(f'dispersion.p90_gt{threshold}.orders_pct', 100*n/int(dispersion.n_pedidos.sum()), path, 'n_pedidos', {'p90_record_to_mean_km_gt':threshold}, '100 × selected sum / total sum')
    mask = dispersion.max_record_to_mean_km > 20
    add('dispersion.extreme.prefixes', int(mask.sum()), path, 'max_record_to_mean_km', {'gt':20}, 'count')
    add('dispersion.extreme.orders', int(dispersion.loc[mask, 'n_pedidos'].sum()), path, 'n_pedidos', {'max_record_to_mean_km_gt':20}, 'sum')
    mask = dispersion.median_shift_km > 1
    add('dispersion.median_shift.prefixes', int(mask.sum()), path, 'median_shift_km', {'gt':1}, 'count')
    add('dispersion.median_shift.orders', int(dispersion.loc[mask, 'n_pedidos'].sum()), path, 'n_pedidos', {'median_shift_km_gt':1}, 'sum')
    add('dispersion.median_shift.maximum', float(dispersion.median_shift_km.max()), path, 'median_shift_km', {}, 'max')
    network_path = args.sensitivity_dir/'sensitivity_network_diagnostics.csv'
    networks = pd.read_csv(network_path)
    record_reference = (networks['case'] == 'main') | ((networks['case'] == 'J_all828_legacy_order') & (networks.radius_km == 3) & networks.method.isin(['P-Median', 'MCLP']))
    for radius, group in networks[record_reference].groupby('radius_km'):
        for field in ['redistributed_coverage_pct']:
            for aggregation in ['min', 'max']:
                add(f'redistributed.main.{int(radius)}.{aggregation}', float(getattr(group[field], aggregation)()), network_path, field, {'cases':['main','J_all828_legacy_order for discrete R3 only'],'radius_km':radius}, aggregation)
    omission_path = args.sensitivity_dir/'omission_hypotheses.csv'
    omissions = pd.read_csv(omission_path)
    add('omissions.total', len(omissions), omission_path, 'order_id', {}, 'count')
    for city in ['papucaia', 'japuiba', 'travessao', 'tocos', 'boa esperanca']:
        add('omissions.'+city, int((omissions.city_norm == city).sum()), omission_path, 'city_norm', {'city_norm':city}, 'count')
    municipal_path = args.main_dir/'service_by_municipality_v22.csv'
    municipalities = pd.read_csv(municipal_path)
    for city, municipality_group in municipalities.groupby('city_norm'):
        assert municipality_group.orders.nunique() == 1
        add('municipality_denominator.'+city, int(municipality_group.iloc[0].orders), municipal_path, 'orders', {'city_norm':city}, 'unique denominator')
    for _, municipal_row in municipalities[(municipalities.scope == 'main') & (municipalities.radius_km == 10)].iterrows():
        add(f'municipality_pct.{municipal_row.method}.10.{municipal_row.city_norm}', float(municipal_row.coverage_pct), municipal_path, 'coverage_pct', {'scope':'main','method':municipal_row.method,'radius_km':10,'city_norm':municipal_row.city_norm})
    group = municipalities[municipalities.city_norm == 'cachoeiras de macacu']
    assert group.orders.nunique() == 1
    included = int(group.iloc[0].orders)
    additions = int(omissions.city_norm.isin(['papucaia','japuiba']).sum())
    add('omissions.cachoeiras_included', included, municipal_path, 'orders', {'city_norm':'cachoeiras de macacu'}, 'unique denominator')
    add('omissions.cachoeiras_potential', included+additions, omission_path, 'city_norm', {'city_norm_in':['papucaia','japuiba']}, f'count + original denominator {included}')
    add('omissions.cachoeiras_additions_share', 100*additions/(included+additions), omission_path, 'city_norm', {'city_norm_in':['papucaia','japuiba']}, '100 × count / potential denominator')
    for _, row in selected[selected.K_selected.notna()].iterrows():
        prefix = f'main.{row.scope}.{row.method}.{int(row.radius_km)}'
        add(prefix+'.coverage_margin_orders', int(row.covered_orders-row.required_orders), args.main_dir/'service_selection.csv', 'covered_orders,required_orders', {'scope':row.scope,'method':row.method,'radius_km':row.radius_km}, 'covered_orders − required_orders')
    payload = dict(values=values, source_hashes=sources,
                   policy='Scientific values are computed from completed results; manuscript formatting only rounds these values. No value is copied from the final DOCX.')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'values':len(values),'sources':len(sources),'output':str(args.out)}))


if __name__ == '__main__':
    main()
