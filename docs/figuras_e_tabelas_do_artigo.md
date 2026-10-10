# Figuras e tabelas do artigo: onde estão e como foram calculadas

Este guia liga cada figura e tabela da versão final do artigo aos arquivos do
commit científico congelado
[e688d15](https://github.com/brunomoraes87/pickup-points-rmrj/tree/e688d15cc475e58bef9128ff5bbc8fa036fe50f4),
o mesmo citado no artigo. O Apêndice A.6 do artigo traz a mesma correspondência.
Este guia foi publicado depois dessa versão e não existe dentro dela: ele fica no
`main`, e todos os links de arquivos abaixo apontam para o commit e688d15.

A numeração dos arquivos não segue a do artigo. Há figuras com o mesmo nome em
pastas de versões anteriores (`figures/` e `figures/service_selection/`): as do
artigo são as de `figures/v22_verified/` e `figures/v23_verified/`.

## Figuras

| Artigo | Arquivo | Script que desenha | Dados plotados | Cálculo |
|---|---|---|---|---|
| Figura 1 | [10_instalacoes_por_raio.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/figures/v22_verified/10_instalacoes_por_raio.png) | [09_plot_v22.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/09_plot_v22.py) | [service_selection.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/main/service_selection.csv): `K_selected`, `status` | [05_select_service_k.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/05_select_service_k.py) |
| Figura 2 | [11_perfis_selecionados_R3.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/figures/v22_verified/11_perfis_selecionados_R3.png) | 09_plot_v22.py | service_selection.csv, `radius_km` = 3: `K_selected`, `weighted_avg_distance_km`, `p99_empirical_km`, `max_distance_km` | 05_select_service_k.py |
| Figura 3 | [12_mapas_selecao_R3.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/figures/v22_verified/12_mapas_selecao_R3.png) | 09_plot_v22.py | [service_facilities.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/main/service_facilities.csv), [service_assignments.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/main/service_assignments.csv), [demanda_por_cep.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/demanda_por_cep.csv), [rj_municipios_ibge.geojson](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/geography/rj_municipios_ibge.geojson); três maiores deslocamentos em [figure_map_extremes_v22.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/main/figure_map_extremes_v22.csv) | 05_select_service_k.py |
| Figura 4 | [16_mapas_perfis_R3_v23.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/figures/v23_verified/16_mapas_perfis_R3_v23.png) | [15geracao_figuras_verificadas.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/15geracao_figuras_verificadas.py) | redes J825_R3_T8 e J825_R3_T4p65 em [profiles/networks/](https://github.com/brunomoraes87/pickup-points-rmrj/tree/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v23_verified/profiles/networks); redes de Ward e Average em service_facilities.csv; três maiores deslocamentos em [tres_maiores_deslocamentos.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/figures/v23_verified/tres_maiores_deslocamentos.csv) | [13_certify_service_profiles_v23.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/13_certify_service_profiles_v23.py) |
| Figura A.1 (Apêndice A.5) | [17_comparacao_perfis_R3_v23.png](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/figures/v23_verified/17_comparacao_perfis_R3_v23.png) | 15geracao_figuras_verificadas.py | [valores_plotados.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/figures/v23_verified/valores_plotados.csv), extraído de [all_network_profiles.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v23_verified/profiles/all_network_profiles.csv) | 13_certify_service_profiles_v23.py |

## Tabelas

| Artigo | Arquivo | Produzido por | Campos |
|---|---|---|---|
| Tabelas 1, 2 e A.2 | [data/v22_verified/main/service_selection.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/main/service_selection.csv) | 05_select_service_k.py | `K_selected`, `status`, `coverage_pct`, `weighted_avg_distance_km`, `median_empirical_km`, `p95_empirical_km`, `p99_empirical_km`, `max_distance_km`, `runtime_s`, `search_runtime_s` |
| Tabelas 3 e 6 | [data/v22_verified/exact/exact_results.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/exact/exact_results.csv) | [07_run_exact_benchmarks.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/07_run_exact_benchmarks.py) | linhas `partial_*` (Tabela 3) e `proximity_J828_R3_*` (Tabela 6): `K`, `mip_gap`, `max_distance_km`, `coverage_pct` |
| Tabela 4 | [data/v22_verified/main/municipal_summary_v22.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/main/municipal_summary_v22.csv) | 09_plot_v22.py | `zero_coverage_municipalities`, `below_80pct_municipalities`, `outside_orders`, `rio_outside_orders`, `rio_share_outside_pct` |
| Tabela 5 | [data/v22_verified/main/service_by_municipality_v22.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/main/service_by_municipality_v22.csv) | 09_plot_v22.py | `radius_km` = 10: `orders`, `coverage_pct` por município |
| Tabelas 7 e A.1 | [data/v22_verified/sensitivity/sensitivity_selection.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/sensitivity/sensitivity_selection.csv) | [08_run_sensitivities.py](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/08_run_sensitivities.py), com robustness_v22.py | `K_selected` e `status` por `case`, `method` e `radius_km` |
| Tabela 8 | [data/v23_verified/profiles/solver_profiles.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v23_verified/profiles/solver_profiles.csv) | 13_certify_service_profiles_v23.py | redes `J825_R3_T8`, `J825_R3_T5`, `J825_R3_T4p65`; redes principais em service_selection.csv e municipal_summary_v22.csv |

O Quadro 1 e a Tabela 9 não têm arquivo próprio: reúnem definições e resultados
das demais tabelas. Os demais números do texto estão, item a item, em
[conferencia_numeros_versao_final.csv](conferencia_numeros_versao_final.csv).

## Funções que fazem o cálculo

Os scripts de desenho (09 e 15) só leem resultados já calculados. O cálculo fica
nas funções abaixo, no commit e688d15; cada link abre as linhas da função.

Figuras 1, 2 e 3; Tabelas 1, 2 e A.2:

| Etapa | Função | Onde |
|---|---|---|
| Pedidos exigidos pela meta de 95% (9.207) | `required_orders` | [05_select_service_k.py, linhas 58–64](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/05_select_service_k.py#L58-L64) |
| Mediana, P95 e P99 empíricos, ponderados por pedidos | `empirical_quantile` | [05_select_service_k.py, linhas 67–77](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/05_select_service_k.py#L67-L77) |
| Cobertura, média, P95, P99 e máximo de uma rede em cada raio | `radius_metrics` | [05_select_service_k.py, linhas 80–104](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/05_select_service_k.py#L80-L104) |
| Primeiro K que atende à meta, depois de testar todos os K menores (K-Means: nas cinco sementes) | `first_feasible_k` | [05_select_service_k.py, linhas 115–131](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/05_select_service_k.py#L115-L131) |
| MCLP por Greedy Adding | `mclp_greedy_trajectory` | [05_select_service_k.py, linhas 143–167](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/05_select_service_k.py#L143-L167) |
| Ajuste de K-Means ponderado, Ward, Complete, Average e p-mediana em cada K | `ServiceSearch.fit` | [05_select_service_k.py, linhas 317–347](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/05_select_service_k.py#L317-L347) |
| Registro da rede selecionada e das métricas exportadas | `ServiceSearch.select` | [05_select_service_k.py, linhas 372–398](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/05_select_service_k.py#L372-L398) |
| Centro ponderado e agrupamentos hierárquicos | `weighted_centroid`, `method_agglomerative` | [methods.py, linhas 36–65](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/methods.py#L36-L65) |
| P-mediana por construção gulosa e trocas | `method_pmedian_heuristic` | [methods.py, linhas 182–250](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/methods.py#L182-L250) |
| Escolha dos 300 candidatos de maior demanda, com desempate pelo prefixo | `select_candidate_indices` | [candidate_sets.py, linhas 31–67](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/candidate_sets.py#L31-L67) |

Tabela 8; Figuras 4 e A.1:

| Etapa | Função | Onde |
|---|---|---|
| Percentis, métricas e perfil municipal das alternativas exatas | `empirical`, `metrics`, `municipal_profile` | [13_certify_service_profiles_v23.py, linhas 61–94](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/13_certify_service_profiles_v23.py#L61-L94) |
| Menor quantidade de instalações, com proximidade obrigatória opcional (otimização inteira) | `solve_count` | [13_certify_service_profiles_v23.py, linhas 97–157](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/scripts/13_certify_service_profiles_v23.py#L97-L157) |

## Como refazer as figuras

Use o ambiente de `requirements-reproduction.txt` e uma pasta de saída vazia. O que
roda apenas com os arquivos do repositório depende da versão:

| Figuras | No commit e688d15, citado no artigo | No `main`, a partir do commit [b19ac3d](https://github.com/brunomoraes87/pickup-points-rmrj/commit/b19ac3d7a9c4613a9c3205f9a52adc22fef08af9) |
|---|---|---|
| 4 e A.1 (script 15) | roda | roda |
| 1, 2 e 3 (script 09) | exige a pasta `checkpoints/`, gerada pela execução completa da busca e mantida fora do Git | roda: sem `checkpoints/`, usa as curvas exportadas em `frontier_curves_v22.csv` |

### Figuras 4 e A.1: commit e688d15 ou `main`

```text
python scripts/15geracao_figuras_verificadas.py --profiles data/v23_verified/profiles --output pasta_nova_vazia
```

Gera as Figuras 4 e A.1 e os arquivos `valores_plotados.csv` e
`tres_maiores_deslocamentos.csv`. Num teste em 10/10/2026, os quatro arquivos
saíram idênticos byte a byte aos de `figures/v23_verified/`. Os caminhos `C:\...`
gravados nos manifestos registram onde os arquivos estavam na execução original;
o script usa os campos `repo_relative`, que apontam para este repositório.

Para perfis novos, rode antes o script 14 sem `--report`: assim ele grava
`independent_verification.json` dentro da pasta dos perfis, arquivo que o script 15
exige (comandos completos no README). Num teste em 10/10/2026 com uma cópia dos
perfis congelados, essa sequência gerou figuras e CSVs idênticos byte a byte aos
de `figures/v23_verified/`; com `--report` fora da pasta, o script 15 parou por
falta desse arquivo.

### Figuras 1, 2 e 3: `main`, ou qualquer commit a partir de b19ac3d

```text
python scripts/09_plot_v22.py --data-dir data --results-dir copia_de_data_v22_verified_main --figures-dir pasta_nova_vazia
```

O script grava CSVs auxiliares em `--results-dir`; por isso, use uma cópia de
`data/v22_verified/main`. Quando encontra a pasta `checkpoints/`, ele recalcula as
curvas de K a partir dela. Sem essa pasta, usa as curvas exportadas em
[frontier_curves_v22.csv](https://github.com/brunomoraes87/pickup-points-rmrj/blob/e688d15cc475e58bef9128ff5bbc8fa036fe50f4/data/v22_verified/main/frontier_curves_v22.csv),
sem regravá-las. No commit e688d15, o script ainda exige os checkpoints.

Num teste em 10/10/2026, a partir de b19ac3d, as nove figuras de
`figures/v22_verified/` desenhadas por este script e os CSVs das Tabelas 4 e 5
saíram idênticos byte a byte aos do repositório, e nenhum CSV de
`data/v22_verified/main` mudou. Os 78 testes e 230 subtestes do repositório
passaram. Use uma pasta de figuras vazia: o `figure_manifest.json` lista todos os
PNG da pasta de destino.

Os scripts de cálculo partem dos dados públicos da Olist, identificados por
hashes em `data/quality/summary.json`; a ordem completa de execução está no README.
