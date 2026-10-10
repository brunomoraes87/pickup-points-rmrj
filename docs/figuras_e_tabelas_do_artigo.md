# Figuras e tabelas do artigo: onde estão e como foram calculadas

Este guia liga cada figura e tabela da versão final do artigo aos arquivos do
commit científico congelado
[952ee3a](https://github.com/brunomoraes87/pickup-points-rmrj/tree/952ee3a26e4b47a69ca2491b2420507df8ed8498),
o mesmo citado no artigo. O Apêndice A.6 do artigo traz a mesma correspondência.

A numeração dos arquivos não segue a do artigo. Há figuras com o mesmo nome em
pastas de versões anteriores (`figures/` e `figures/service_selection/`): as do
artigo são as de `figures/v22_verified/` e `figures/v23_verified/`.

## Figuras

| Artigo | Arquivo | Script que desenha | Dados plotados | Cálculo |
|---|---|---|---|---|
| Figura 1 | [10_instalacoes_por_raio.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/figures/v22_verified/10_instalacoes_por_raio.png) | [09_plot_v22.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/scripts/09_plot_v22.py) | [service_selection.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/main/service_selection.csv): `K_selected`, `status` | [05_select_service_k.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/scripts/05_select_service_k.py) |
| Figura 2 | [11_perfis_selecionados_R3.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/figures/v22_verified/11_perfis_selecionados_R3.png) | 09_plot_v22.py | service_selection.csv, `radius_km` = 3: `K_selected`, `weighted_avg_distance_km`, `p99_empirical_km`, `max_distance_km` | 05_select_service_k.py |
| Figura 3 | [12_mapas_selecao_R3.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/figures/v22_verified/12_mapas_selecao_R3.png) | 09_plot_v22.py | [service_facilities.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/main/service_facilities.csv), [service_assignments.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/main/service_assignments.csv), [demanda_por_cep.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/demanda_por_cep.csv), [rj_municipios_ibge.geojson](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/geography/rj_municipios_ibge.geojson); três maiores deslocamentos em [figure_map_extremes_v22.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/main/figure_map_extremes_v22.csv) | 05_select_service_k.py |
| Figura 4 | [16_mapas_perfis_R3_v23.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/figures/v23_verified/16_mapas_perfis_R3_v23.png) | [15geracao_figuras_verificadas.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/scripts/15geracao_figuras_verificadas.py) | redes J825_R3_T8 e J825_R3_T4p65 em [profiles/networks/](https://github.com/brunomoraes87/pickup-points-rmrj/tree/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v23_verified/profiles/networks); redes de Ward e Average em service_facilities.csv; três maiores deslocamentos em [tres_maiores_deslocamentos.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/figures/v23_verified/tres_maiores_deslocamentos.csv) | [13_certify_service_profiles_v23.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/scripts/13_certify_service_profiles_v23.py) |
| Figura A.1 (Apêndice A.5) | [17_comparacao_perfis_R3_v23.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/figures/v23_verified/17_comparacao_perfis_R3_v23.png) | 15geracao_figuras_verificadas.py | [valores_plotados.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/figures/v23_verified/valores_plotados.csv), extraído de [all_network_profiles.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v23_verified/profiles/all_network_profiles.csv) | 13_certify_service_profiles_v23.py |

## Tabelas

| Artigo | Arquivo | Produzido por | Campos |
|---|---|---|---|
| Tabelas 1, 2 e A.2 | [data/v22_verified/main/service_selection.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/main/service_selection.csv) | 05_select_service_k.py | `K_selected`, `status`, `coverage_pct`, `weighted_avg_distance_km`, `median_empirical_km`, `p95_empirical_km`, `p99_empirical_km`, `max_distance_km`, `runtime_s`, `search_runtime_s` |
| Tabelas 3 e 6 | [data/v22_verified/exact/exact_results.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/exact/exact_results.csv) | [07_run_exact_benchmarks.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/scripts/07_run_exact_benchmarks.py) | linhas `partial_*` (Tabela 3) e `proximity_J828_R3_*` (Tabela 6): `K`, `mip_gap`, `max_distance_km`, `coverage_pct` |
| Tabela 4 | [data/v22_verified/main/municipal_summary_v22.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/main/municipal_summary_v22.csv) | 09_plot_v22.py | `zero_coverage_municipalities`, `below_80pct_municipalities`, `outside_orders`, `rio_outside_orders`, `rio_share_outside_pct` |
| Tabela 5 | [data/v22_verified/main/service_by_municipality_v22.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/main/service_by_municipality_v22.csv) | 09_plot_v22.py | `radius_km` = 10: `orders`, `coverage_pct` por município |
| Tabelas 7 e A.1 | [data/v22_verified/sensitivity/sensitivity_selection.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/sensitivity/sensitivity_selection.csv) | [08_run_sensitivities.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/scripts/08_run_sensitivities.py), com robustness_v22.py | `K_selected` e `status` por `case`, `method` e `radius_km` |
| Tabela 8 | [data/v23_verified/profiles/solver_profiles.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v23_verified/profiles/solver_profiles.csv) | 13_certify_service_profiles_v23.py | redes `J825_R3_T8`, `J825_R3_T5`, `J825_R3_T4p65`; redes principais em service_selection.csv e municipal_summary_v22.csv |

O Quadro 1 e a Tabela 9 não têm arquivo próprio: reúnem definições e resultados
das demais tabelas. Os demais números do texto estão, item a item, em
[conferencia_numeros_versao_final.csv](conferencia_numeros_versao_final.csv).

## Como refazer as figuras

Na raiz do repositório, no commit 952ee3a, com o ambiente de
`requirements-reproduction.txt`:

```text
python scripts/15geracao_figuras_verificadas.py --profiles data/v23_verified/profiles --output pasta_nova_vazia
```

Gera as Figuras 4 e A.1 e os arquivos `valores_plotados.csv` e
`tres_maiores_deslocamentos.csv`. Num teste em 10/10/2026, os quatro arquivos
saíram idênticos byte a byte aos de `figures/v23_verified/`. Os caminhos `C:\...`
gravados nos manifestos registram onde os arquivos estavam na execução original;
o script usa os campos `repo_relative`, que apontam para este repositório.

```text
python scripts/09_plot_v22.py --data-dir data --results-dir copia_de_data_v22_verified_main --figures-dir pasta_nova_vazia
```

Gera as Figuras 1, 2 e 3. O script grava CSVs auxiliares em `--results-dir`; por
isso, use uma cópia de `data/v22_verified/main`. Quando encontra a pasta
`checkpoints/`, gerada pela pipeline completa e mantida fora do Git, ele recalcula
as curvas de K a partir dela. Sem essa pasta, usa as curvas exportadas em
[frontier_curves_v22.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/952ee3a26e4b47a69ca2491b2420507df8ed8498/data/v22_verified/main/frontier_curves_v22.csv),
sem regravá-las. Esse caminho existe a partir do commit
[bb294ac](https://github.com/brunomoraes87/pickup-points-rmrj/commit/bb294ac277005a03e893daf94016d360dc857564);
no commit 952ee3a, citado no artigo, o script ainda exige os checkpoints.

Num teste em 10/10/2026, a partir de bb294ac, as nove figuras de
`figures/v22_verified/` desenhadas por este script e os CSVs das Tabelas 4 e 5
saíram idênticos byte a byte aos do repositório, e nenhum CSV de
`data/v22_verified/main` mudou. Os 78 testes e 230 subtestes do repositório
passaram. Use uma pasta de figuras vazia: o `figure_manifest.json` lista todos os
PNG da pasta de destino.

Os scripts de cálculo partem dos dados públicos da Olist, identificados por
hashes em `data/quality/summary.json`; a ordem completa de execução está no README.
