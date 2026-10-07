# Localização de pontos de retirada na RMRJ

Material de reprodução da versão revisada do manuscrito de Bruno M. Moraes.
O experimento usa **9.691 pedidos entregues, agregados em 828 prefixos de CEP**.
O recorte inclui os 22 municípios da Lei Complementar estadual 184/2018.

## Métodos e seleção por cobertura

A comparação principal busca, para cada configuração, o **primeiro K inteiro
encontrado que cobre pelo menos 95% dos pedidos** nos cenários exploratórios
R=3, 5 e 10 km. Cada método pode selecionar uma quantidade diferente de PUs.
Os raios não são SLAs validados e o K selecionado não é um ótimo econômico
nem prova do mínimo global do problema.

Quatro famílias produzem seis configurações: K-Means ponderado, aglomerativo
(Ward, complete, average), p-mediana por construção/trocas e MCLP guloso.
DBSCAN permanece exploratório: uma busca comparável de epsilon/min_samples
e política para o ruído não foi implementada.

A busca testa cada inteiro desde 1, sem presumir monotonicidade. K-Means usa
sementes 42, 0, 1, 2 e 3 e 10 inicializações por ajuste; o K escolhido deve cumprir a
meta nas cinco sementes. Exportam-se mínimos por semente, intervalos observados
e o ajuste42 representativo. Essa checagem não é uma garantia probabilística.

P-mediana e MCLP usam os mesmos 300 prefixos de maior demanda como candidatos,
mantendo os 828 pontos na avaliação. O teto de cobertura desse conjunto em 3 km
é 93,685%: ambos são estruturalmente inviáveis para 95% nessa condição.
A sensibilidade com todos 828 candidatos é exportada separadamente em 3 km.
Os centros contínuos do clustering e os candidatos derivados de CEP não foram
validados como imóveis ou endereços comerciais implementáveis.

P-mediana mantém a heurística original e até 100 iterações; seu motivo de
término não é exposto pela função legada. MCLP usa o raio de cada cenário e
os prefixos de uma única trajetória gulosa equivalente à implementação original,
registrando instalações efetivamente abertas. Tempo do prefixo e da trajetória
completa são distintos; avaliação/exportação ficam fora desses tempos.

A comparação histórica em **K=70** e as curvas antigas permanecem disponíveis
como referência suplementar de orçamento fixo.

## Saneamento antes da média por CEP

1. Verificar chaves únicas e cardinalidade das junções, sem multiplicar pedidos.
2. Selecionar 9.694 pedidos entregues no recorte, com 830 prefixos demandados.
3. Examinar todas as 93.322 coordenadas da fonte ligadas a esses prefixos,
   sem excluir registros apenas pelo texto de cidade/estado.
4. Verificar valores numéricos e pertinência à união inclusiva das malhas
   municipais IBGE. Cada registro externo exige decisão explícita de revisão.
5. Excluir 43 coordenadas claramente externas; manter três registros junto à
   divisa como incerteza cartográfica documentada. Recuperar 76 registros
   compatíveis com o recorte que o filtro textual anterior descartava.
6. Calcular a mesma média aritmética por prefixo, preservando as repetições da
   fonte. Excluir três pedidos sem coordenada aproveitável (24027 e 25919).
7. Confirmar conservação: 9.691 pedidos e 828 prefixos na base final comum.

A malha é a versão simplificada da API IBGE v3, qualidade maxima, consultada
em 06/10/2026 e preservada por SHA256. O ano de referência não é informado na
resposta. Nenhum limiar P95/P99 nem distância a instalações define exclusões.
A checagem regional não comprova a correspondência exata entre coordenada e CEP.

## Reprodução

Obtenha os CSVs públicos do [Olist no Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce),
preservando a versão cujo hash consta em data/geography/scope.json.
Coloque-os em olist_raw/ ou forneça --raw-dir. As entradas são lidas e permanecem intactas.

    pip install -r requirements-reproduction.txt
    python -m unittest discover -s tests -v
    python scripts/01_prepare_data.py --raw-dir /caminho/dos/CSVs
    python scripts/02_run_experiments.py
    python scripts/03_plot_figures.py
    python scripts/04_compare_cleaning.py
    python scripts/05_select_service_k.py
    python scripts/06_plot_service.py

Os caminhos padrão são relativos ao repositório; a execução pode começar em
qualquer diretório. Há opções --data-dir, --k-values e --candidates.
O script03 conserva as figuras históricas K=70 e as curvas K10–160.
O script05 salva a análise nova em data/service_selection, com checkpoint
local por ajuste e assinatura dos dados, código, versões e parâmetros.
Uma alteração dessa assinatura exige outro diretório de saída.
O script06 gera seis figuras em figures/service_selection e diagnósticos
municipais a partir do município de cada pedido, sem multiplicar a demanda.
É possível fornecer --out-dir/--results-dir/--figures-dir.

## Métricas e atribuição

Todas as métricas operacionais usam distância de Haversine ao PU mais próximo.
A cobertura conta pedidos com distância <=R. Nesta base,95% exige pelo menos
**9.207 dos 9.691 pedidos**. P95/P99 empíricos usam a inversa da distribuição
acumulada por pedidos: primeira distância observada que alcança ceil(q*N).
Essa definição mantém P95<=R equivalente à meta, sem interpolação na decisão.

Percentis lineares são exportados para compatibilidade com a revisão anterior.
Na análise histórica K70, mediana/P95/P99 usam interpolação linear sobre
np.repeat(distâncias,n_pedidos), com percentis não ponderados de CEP à parte.
Os arquivos novos identificam claramente as duas convenções.

A seleção é externa aos ajustes: **P95 global não delimita cada cluster,
não elimina pontos distantes e não garante 95% em cada município**.
Todos os pedidos permanecem atribuídos, inclusive os além do raio.
P99, máximo, pedidos fora, mapas e diagnóstico municipal expõem essa cauda.
Grupos nativos e atribuição operacional são exportados separadamente.

Ward/KMeans ajustam graus euclidianos; complete/average usam Haversine.
A avaliação usa Haversine para todos. A área de convex hull do experimento
histórico descreve os grupos nativos em EPSG31983, não território operacional.

## Instalações selecionadas por cenário

| Configuração | Candidatos | K em 3 km | K em 5 km | K em 10 km |
|---|---|---:|---:|---:|
| K-Means | centros contínuos | 82 | 40 | 17 |
| Ward | centros contínuos | 80 | 42 | 17 |
| Complete | centros contínuos | 88 | 46 | 19 |
| Average | centros contínuos | 99 | 53 | 24 |
| P-mediana | 300 | inviável* | 55 | 23 |
| MCLP | 300 | inviável* | 40 | 15 |
| P-mediana (sensibilidade) |828 |90 |— |— |
| MCLP (sensibilidade) |828 |64 |— |— |

*Inviabilidade estrutural do conjunto300 em 3 km; teto93,685%, antes da busca.
A sensibilidade828 é outra condição, não parte do ranking300.
Os números são mínimos encontrados pelas soluções produzidas e a regra de
sementes, não mínimos globais ou economicamente ótimos.

## Referência histórica em K=70

| Método | Média km | Cobertura3km % | P95km | P99km | Máximo km |
|---|---:|---:|---:|---:|---:|
| KMeans-weighted | 1.491 | 92.705 | 3.254 | 4.854 | 15.265 |
| Agglomerative-ward | 1.767 | 90.424 | 3.339 | 5.155 | 8.477 |
| Agglomerative-complete | 1.923 | 85.223 | 3.820 | 4.555 | 6.264 |
| Agglomerative-average | 2.150 | 75.121 | 4.004 | 4.558 | 6.152 |
| P-Median | 1.446 | 88.587 | 4.311 | 8.491 | 16.550 |
| MCLP-R3km | 1.760 | 92.601 | 4.311 | 8.491 | 16.550 |

P-median tem a menor média. K-Means tem a maior cobertura3km e o menor P95.
Average tem o menor máximo; complete oferece média e cobertura melhores com
máximo próximo. A antiga cauda de160km desaparece após o saneamento e não
fundamenta a eliminação de p-median/MCLP. K=90 altera a liderança de cobertura
entre K-Means e Ward; as conclusões dependem de K e da prioridade operacional.

## Arquivos de auditoria e reprodução

- data/geography/: malha exata, escopo e decisões revisadas com identidade da linha.
- data/quality/: resumo, quarentena, casos de divisa, registros recuperados e pedidos excluídos.
- data/quality/geolocation_audit.csv: auditoria completa local, gerada pelo pipeline e omitida do Git pelo volume.
- data/paper_table_K70.csv: seis configurações comuns.
- data/facilities_K70.csv e assignments_K70.csv: instalações e atribuições nativas/operacionais.
- data/reference_curves_K10_K160.csv: valores usados na figura de sensibilidade.
- data/experiment_metadata.json: hashes, versões, candidatos, semente e convenções.
- figures/09_grupos_nativos_vs_ponto_proximo.png: exemplos das diferenças de atribuição.
- data/service_selection/service_curves.csv: cadaK/semente/raio testado.
- data/service_selection/service_selection.csv: seleções e inviabilidade estrutural.
- data/service_selection/service_seed_first_k.csv: primeiroK viável de cada semente.
- data/service_selection/service_facilities.csv e service_assignments.csv: redes selecionadas e todos os pedidos.
- data/service_selection/service_tails.csv e service_by_municipality.csv: cauda e cobertura municipal.
- data/service_selection/service_map_extremes.csv e service_native_examples.csv: exemplos visuais verificáveis.
- data/service_selection/service_metadata.json: assinatura, hashes, convenções e limites.
- figures/service_selection/: contagens, caudas, mapas3/5/10 e formação versus PU próximo.
- scripts/ e tests/: implementação e verificações analíticas.

## Limites

CEP disponível apenas em prefixos de cinco dígitos; médias e centros podem cair
sobre água ou locais sem elegibilidade comercial. Coordenadas internas ao recorte
também podem conter erros não detectados. Dados2016–2018 não representam demanda
atual. Distâncias esféricas não modelam vias, travessias, tempo, capacidade,
custos imobiliários ou escolha do consumidor. Nenhuma localização proposta foi
validada como ponto comercial implementável nem como cumprimento de SLA.

## Fontes e licença

[Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce),
[malhas IBGE](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3) e
[Lei Complementar184/2018](https://www.rj.gov.br/irm/sites/default/files/2023-04/lei-complementar-184.pdf).
Código sob MIT, conforme LICENSE. Os dados Olist derivados permanecem sujeitos
aos termos da fonte original; esta revisão não concede uma licença diferente.

A auditoria das médias derivadas sinaliza três prefixos (21941,22291,24370),
com 35 pedidos, fora da união municipal. Permanecem como aproximações espaciais;
não são endereços certificados. Ver quality/aggregated_means_outside_region.csv.

A comparação controlada antes/depois usa os mesmos métodos, K=70 e 300 candidatos.
Ver data/cleaning_sensitivity_K70.csv e scripts/04_compare_cleaning.py.
