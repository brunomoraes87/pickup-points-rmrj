# Dados processados da versão revisada

> Este arquivo descreve os dados derivados do Olist e saídas de versões anteriores do
> estudo, feitas com orçamento fixo K=70. No artigo final, a demanda vem de
> `demanda_por_cep.csv` e `pedidos_rmrj_geo.csv`, e as saídas estão em `v22_verified/`
> e `v23_verified/`; o [guia de figuras e tabelas](../docs/figuras_e_tabelas_do_artigo.md)
> liga cada figura e tabela aos arquivos. Os arquivos com K70 no nome,
> `native_assignment_examples.csv` e `reference_curves_K10_K160.csv` são históricos;
> `results_full.csv` e `results_clustering.csv` guardam também os resultados
> exploratórios do DBSCAN citados no artigo.

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
