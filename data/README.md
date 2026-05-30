# Dados processados

Arquivos derivados do dataset público Olist, filtrados para a Região Metropolitana do Rio de Janeiro.

## Arquivos

| Arquivo | Descrição | Linhas |
|---|---|---|
| `demanda_por_cep.csv` | Pontos de demanda agregados por CEP | 829 |
| `pedidos_rmrj_geo.csv` | Pedidos com geolocalização válida | 9.692 |
| `clientes_rmrj.csv` | Clientes residentes na RMRJ | 10.107 |
| `geo_rmrj_agg.csv` | Coordenadas médias por CEP da RMRJ | 961 |
| `results_full.csv` | Resultados de todas as 38 configurações experimentais | 38 |
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

## Fonte original

Brazilian E-Commerce Public Dataset by Olist, disponível em:
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

Período: outubro/2016 a agosto/2018.
