# Dados processados da versão revisada

Dados derivados do Olist. A preparação, a validação regional e as convenções de
avaliação estão descritas no README principal. A base comum contém 9.691 pedidos
e 828 prefixos de CEP. Os arquivos originais são externos ao Git e permanecem intactos.

| Arquivo | Linhas |
|---|---:|
| assignments_K70.csv | 4,968 |
| clientes_rmrj.csv | 10,107 |
| demanda_por_cep.csv | 828 |
| facilities_K70.csv | 420 |
| geo_rmrj_agg.csv | 828 |
| native_assignment_examples.csv | 6 |
| paper_table_K70.csv | 6 |
| pedidos_rmrj_geo.csv | 9,691 |
| reference_curves_K10_K160.csv | 48 |
| results_clustering.csv | 36 |
| results_full.csv | 64 |

Os CSVs de métricas usam ponto decimal e distância em km. O prefixo original
é customer_zip_code_prefix na demanda; CEP nas exportações de atribuições.
O campo city_norm é informação da origem do cliente, não validação postal.
summary.json contém a conservação de demanda e a contagem dos descartes.
O relatório completo geolocation_audit.csv é gerado localmente pelo pipeline.

A auditoria das médias derivadas sinaliza três prefixos (21941,22291,24370),
com 35 pedidos, fora da união municipal. Permanecem como aproximações espaciais;
não são endereços certificados. Ver quality/aggregated_means_outside_region.csv.
