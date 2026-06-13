"""
01_prepare_data.py
==================
Filtra o dataset Olist para a Região Metropolitana do Rio de Janeiro (RMRJ)
e agrega a demanda por CEP.

Entrada: 4 CSVs brutos do Olist (baixar do Kaggle)
  - olist_customers_dataset.csv
  - olist_geolocation_dataset.csv
  - olist_orders_dataset.csv
  - olist_order_items_dataset.csv

Saída em data/:
  - clientes_rmrj.csv
  - geo_rmrj_agg.csv
  - pedidos_rmrj_geo.csv
  - demanda_por_cep.csv  (arquivo principal — entrada dos experimentos)
"""
import pandas as pd
import numpy as np
import unicodedata
from pathlib import Path

# Caminhos — ajuste UPLOADS para onde você baixou os CSVs do Kaggle
UPLOADS = Path("../olist_raw")        # pasta com os CSVs originais
OUTDIR  = Path("../data")              # onde salvar os processados
OUTDIR.mkdir(parents=True, exist_ok=True)

# Municípios oficiais da RMRJ (Lei Complementar Estadual 184/2018)
RMRJ_MUNICIPIOS = [
    'rio de janeiro', 'belford roxo', 'cachoeiras de macacu', 'duque de caxias',
    'guapimirim', 'itaborai', 'itaguai', 'japeri', 'mage', 'marica',
    'mesquita', 'nilopolis', 'niteroi', 'nova iguacu', 'paracambi',
    'queimados', 'rio bonito', 'sao goncalo', 'sao joao de meriti',
    'seropedica', 'tangua', 'petropolis'
]

def normalize(s):
    if pd.isna(s): return s
    s = str(s).lower().strip()
    return unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode('ascii')

def main():
    print("Carregando dados Olist...")
    customers = pd.read_csv(UPLOADS / "olist_customers_dataset.csv")
    geo       = pd.read_csv(UPLOADS / "olist_geolocation_dataset.csv")
    orders    = pd.read_csv(UPLOADS / "olist_orders_dataset.csv")
    items     = pd.read_csv(UPLOADS / "olist_order_items_dataset.csv")

    customers['city_norm'] = customers['customer_city'].apply(normalize)
    geo['city_norm'] = geo['geolocation_city'].apply(normalize)

    # Filtra clientes da RMRJ
    mask_cli = (customers['customer_state']=='RJ') & (customers['city_norm'].isin(RMRJ_MUNICIPIOS))
    clientes_rmrj = customers[mask_cli].copy()
    print(f"  Clientes RMRJ: {len(clientes_rmrj):,}")
    clientes_rmrj.to_csv(OUTDIR / "clientes_rmrj.csv", index=False)

    # Filtra geolocalização da RMRJ e agrega por CEP
    mask_geo = (geo['geolocation_state']=='RJ') & (geo['city_norm'].isin(RMRJ_MUNICIPIOS))
    geo_rmrj = geo[mask_geo]
    geo_agg = geo_rmrj.groupby('geolocation_zip_code_prefix').agg(
        lat=('geolocation_lat','mean'),
        lng=('geolocation_lng','mean'),
        city=('geolocation_city','first'),
        n_records=('geolocation_lat','count')
    ).reset_index()
    print(f"  Geo agregado por CEP: {len(geo_agg):,}")
    geo_agg.to_csv(OUTDIR / "geo_rmrj_agg.csv", index=False)

    # Filtra pedidos entregues
    ord_clean = orders[orders['order_status']=='delivered'].copy()

    # Adiciona valor agregado por pedido
    items_agg = items.groupby('order_id').agg(
        n_items=('order_item_id','count'),
        total_price=('price','sum'),
        total_freight=('freight_value','sum')
    ).reset_index()
    ord_full = ord_clean.merge(items_agg, on='order_id', how='left')
    ord_full = ord_full.merge(
        customers[['customer_id','customer_zip_code_prefix','city_norm','customer_state']],
        on='customer_id', how='left'
    )

    # Pedidos da RMRJ
    ped_rmrj = ord_full[(ord_full['customer_state']=='RJ') & (ord_full['city_norm'].isin(RMRJ_MUNICIPIOS))]

    # Adiciona lat/lng via merge com geo_agg
    ped_rmrj = ped_rmrj.merge(
        geo_agg[['geolocation_zip_code_prefix','lat','lng']],
        left_on='customer_zip_code_prefix',
        right_on='geolocation_zip_code_prefix',
        how='left'
    ).dropna(subset=['lat','lng'])
    print(f"  Pedidos RMRJ com geolocalização: {len(ped_rmrj):,}")
    ped_rmrj.to_csv(OUTDIR / "pedidos_rmrj_geo.csv", index=False)

    # Agrega demanda por CEP — arquivo principal
    demanda = ped_rmrj.groupby(['customer_zip_code_prefix','lat','lng','city_norm']).agg(
        n_pedidos=('order_id','count'),
        valor_total=('total_price','sum'),
        freight_total=('total_freight','sum')
    ).reset_index()
    print(f"  Pontos de demanda (CEPs): {len(demanda):,}")
    demanda.to_csv(OUTDIR / "demanda_por_cep.csv", index=False)

    print("Pronto.")

if __name__ == "__main__":
    main()
