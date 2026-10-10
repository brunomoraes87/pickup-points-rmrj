"""Prepare common RMRJ demand after reviewing raw geolocation; inputs are read-only."""
import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
import pandas as pd
from data_quality import validate_geolocation, audit_aggregated_coordinates

REPO = Path(__file__).resolve().parents[1]
RMRJ_MUNICIPIOS = [
    'rio de janeiro', 'belford roxo', 'cachoeiras de macacu', 'duque de caxias',
    'guapimirim', 'itaborai', 'itaguai', 'japeri', 'mage', 'marica',
    'mesquita', 'nilopolis', 'niteroi', 'nova iguacu', 'paracambi',
    'queimados', 'rio bonito', 'sao goncalo', 'sao joao de meriti',
    'seropedica', 'tangua', 'petropolis',
]

def normalize(s):
    if pd.isna(s): return s
    return unicodedata.normalize('NFKD', str(s).lower().strip()).encode('ascii','ignore').decode('ascii')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, default=REPO/'olist_raw')
    parser.add_argument('--out-dir', type=Path, default=REPO/'data')
    parser.add_argument('--geography-dir', type=Path, default=REPO/'data'/'geography')
    args=parser.parse_args()
    out=args.out_dir;out.mkdir(parents=True,exist_ok=True)
    quality=out/'quality';quality.mkdir(exist_ok=True)
    scope=json.loads((args.geography_dir/'scope.json').read_text(encoding='utf-8'))
    geo_path=args.raw_dir/'olist_geolocation_dataset.csv'
    if digest(geo_path)!=scope['original_geolocation_sha256']:
        raise ValueError('Geolocation differs from the reviewed snapshot; review it before preparing demand.')
    if digest(args.geography_dir/'rj_municipios_ibge.geojson')!=scope['geometry_sha256']:
        raise ValueError('IBGE geometry differs from the reviewed snapshot.')
    customers=pd.read_csv(args.raw_dir/'olist_customers_dataset.csv')
    geo=pd.read_csv(geo_path)
    orders=pd.read_csv(args.raw_dir/'olist_orders_dataset.csv')
    items=pd.read_csv(args.raw_dir/'olist_order_items_dataset.csv')
    if customers.customer_id.duplicated().any() or orders.order_id.duplicated().any():
        raise ValueError('Customer/order keys are not unique.')
    if items.duplicated(['order_id','order_item_id']).any():
        raise ValueError('Duplicate order-item key would inflate values.')
    customers['city_norm']=customers.customer_city.map(normalize)
    clientes=customers[(customers.customer_state=='RJ')&customers.city_norm.isin(RMRJ_MUNICIPIOS)].copy()
    clientes.to_csv(out/'clientes_rmrj.csv',index=False)
    items_agg=items.groupby('order_id').agg(n_items=('order_item_id','count'),total_price=('price','sum'),total_freight=('freight_value','sum')).reset_index()
    delivered=orders[orders.order_status=='delivered'].merge(items_agg,on='order_id',how='left',validate='one_to_one')
    delivered=delivered.merge(customers[['customer_id','customer_zip_code_prefix','city_norm','customer_state']],on='customer_id',how='left',validate='many_to_one')
    study=delivered[(delivered.customer_state=='RJ')&delivered.city_norm.isin(RMRJ_MUNICIPIOS)].copy()
    if study.n_items.isna().any():raise ValueError('Delivered study order has no item record.')
    prefixes=study.customer_zip_code_prefix.unique()
    reviews=pd.read_csv(args.geography_dir/'geolocation_review_decisions.csv',float_precision='round_trip')
    clean,audit,geo_summary=validate_geolocation(geo,prefixes,args.geography_dir/'rj_municipios_ibge.geojson',scope['municipality_codes'],reviews)
    # Matching postal prefixes precedes geography: locality/state text alone
    # cannot discard a coordinate compatible with the fixed study region.
    audit.to_csv(quality/'geolocation_audit.csv',index=False)
    audit[audit.status!='inside_region'].to_csv(quality/'geolocation_reviewed.csv',index=False)
    audit[audit.decision.astype(str).str.startswith('exclude')].to_csv(quality/'geolocation_quarantine.csv',index=False)
    legacy=(clean.geolocation_state=='RJ')&clean.geolocation_city.map(normalize).isin(RMRJ_MUNICIPIOS)
    clean[~legacy].to_csv(quality/'geolocation_recovered_from_text_filter.csv',index=False)
    geo_agg=clean.groupby('geolocation_zip_code_prefix').agg(lat=('geolocation_lat','mean'),lng=('geolocation_lng','mean'),city=('geolocation_city','first'),n_records=('geolocation_lat','count')).reset_index()
    joined=study.merge(geo_agg[['geolocation_zip_code_prefix','lat','lng']],left_on='customer_zip_code_prefix',right_on='geolocation_zip_code_prefix',how='left',validate='many_to_one',indicator=True)
    excluded=joined[joined._merge!='both'].copy()
    excluded['exclusion_reason']='No eligible geolocation record for postal prefix'
    excluded.drop(columns=['_merge']).to_csv(quality/'orders_excluded_no_coordinate.csv',index=False)
    included=joined[joined._merge=='both'].drop(columns=['_merge'])
    geo_agg.to_csv(out/'geo_rmrj_agg.csv',index=False)
    included.to_csv(out/'pedidos_rmrj_geo.csv',index=False)
    demand=included.groupby('customer_zip_code_prefix').agg(lat=('lat','first'),lng=('lng','first'),city_norm=('city_norm',lambda s:'; '.join(sorted(set(s)))),n_pedidos=('order_id','count'),valor_total=('total_price','sum'),freight_total=('total_freight','sum')).reset_index()
    if demand.customer_zip_code_prefix.duplicated().any() or (demand.n_pedidos<=0).any() or demand[['lat','lng']].isna().any().any():
        raise ValueError('Invalid aggregated demand.')
    if len(included)+len(excluded)!=len(study) or demand.n_pedidos.sum()!=len(included):
        raise ValueError('Demand conservation failed.')
    demand.to_csv(out/'demanda_por_cep.csv',index=False)
    mean_audit=audit_aggregated_coordinates(demand,args.geography_dir/'rj_municipios_ibge.geojson',scope['municipality_codes'])
    mean_warnings=mean_audit[~mean_audit.mean_inside_region]
    mean_warnings.to_csv(quality/'aggregated_means_outside_region.csv',index=False)
    summary={'scope_municipalities':scope['municipalities'],
             'aggregated_means_outside_region':len(mean_warnings),'orders_with_derived_mean_outside_region':int(mean_warnings.n_pedidos.sum()),'geo_validation':geo_summary,
             'delivered_orders_before_geolocation':len(study),'delivered_orders_retained':len(included),
             'delivered_orders_excluded':len(excluded),'excluded_postal_prefixes':sorted(map(int,excluded.customer_zip_code_prefix.unique())),
             'retained_postal_prefixes':len(demand),'geolocation_rows_recovered_from_text_filter':int((~legacy).sum()),
             'input_hashes':{p.name:digest(p) for p in [args.raw_dir/f'olist_{name}_dataset.csv' for name in ['customers','geolocation','orders','order_items']]},
             'geometry_sha256':scope['geometry_sha256'],'review_decisions_sha256':digest(args.geography_dir/'geolocation_review_decisions.csv'),
             'aggregated_coordinate':'arithmetic mean of retained records; geographic repetitions preserved',
             'region_definition':'inclusive IBGE polygon union; reviewed boundary uncertainty retained explicitly',
             'output_demand_sha256':digest(out/'demanda_por_cep.csv')}
    (quality/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
