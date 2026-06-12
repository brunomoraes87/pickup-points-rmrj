# Dados processados

Arquivos derivados do dataset público Olist, filtrados para a Região Metropolitana do Rio de Janeiro.

## Arquivos

| Arquivo | Descrição | Linhas |
|---|---|---|
| `demanda_por_cep.csv` | Pontos de demanda agregados por CEP | 829 |
| `pedidos_rmrj_geo.csv` | Pedidos com geolocalização válida | 9.692 |
| `clientes_rmrj.csv` | Clientes residentes na RMRJ | 10.107 |
| `geo_rmrj_agg.csv` | Coordenadas médias por CEP da RMRJ | 961 |
| `results_full.csv` | Resultados de todas as configurações experimentais (Agglomerative × 3 linkages, K-Means, P-Median, MCLP × 3 raios, DBSCAN × 8 ε) | 56 |
| `results_clustering.csv` | Subconjunto: métodos de clustering apenas | 32 |

## Esquema — demanda_por_cep.csv (arquivo principal)

| Coluna | Tipo | Descrição |
|---|---|---|
| `customer_zip_code_prefix` | int | Prefixo de 5 dígitos do CEP |
| `lat` | float | Latitude média (graus decimais) |
| `lng` | float | Longitude média (graus decimais) |
| `city_norm` | str | Nome do município (normalizado) |
| `n_pedidos` | int | Número de pedidos entregues no CEP |
| `valor_total` | float | Valor total movimentado (BRL) |
| `freight_total` | float | Frete total (BRL) |

## Esquema — results_full.csv

| Coluna | Tipo | Descrição |
|---|---|---|
| `method` | str | Identificação do método (e.g., `KMeans-weighted`, `MCLP-R3km`) |
| `K_target` | int | Valor de K solicitado (None para DBSCAN) |
| `n_facilities` | int | Número efetivo de facilities (pode diferir de K em MCLP/DBSCAN) |
| `weighted_avg_distance_km` | float | Distância média ponderada por demanda (d̄w) |
| `max_distance_km` | float | Distância máxima ao centroide |
| `p95_distance_km` | float | Percentil 95 da distribuição de distâncias |
| `coverage_3km_%` | float | % da demanda coberta em raio de 3 km |
| `coverage_5km_%` | float | % da demanda coberta em raio de 5 km |
| `coverage_10km_%` | float | % da demanda coberta em raio de 10 km |
| `radius_km` | float | Raio R do MCLP (NaN para outros métodos) |
| `eps_km` | float | Parâmetro ε do DBSCAN (NaN para outros métodos) |
| `n_noise` | int | Número de pontos classificados como ruído pelo DBSCAN (NaN para outros) |
| `runtime_s` | float | Tempo de execução em segundos |

## Fonte original

Brazilian E-Commerce Public Dataset by Olist, disponível em:
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

Período: outubro/2016 a agosto/2018.
