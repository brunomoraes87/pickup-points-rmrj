# Localização de pontos de retirada na RMRJ

Material de reprodução da versão revisada do manuscrito de Bruno M. Moraes.
O experimento usa **9.691 pedidos entregues, agregados em 828 prefixos de CEP**.
O recorte inclui os 22 municípios da Lei Complementar estadual 184/2018.

## Métodos e comparação

Quatro famílias com K controlável geram seis configurações principais:
K-Means ponderado, Agglomerative (Ward, complete, average), p-median por trocas
e MCLP por heurística gulosa. DBSCAN é a quinta família, explorada separadamente.
A tabela principal usa **K=70 para os seis métodos**. Isso é um cenário de
referência e não uma quantidade ótima de instalações demonstrada.

P-median e MCLP usam os mesmos **300 prefixos de maior demanda** como candidatos.
Os métodos de clustering podem posicionar centros fora desse conjunto.
Assim, comparam-se configurações espaciais com escolhas de modelagem distintas,
sem alegar superioridade geral de um algoritmo ou solução globalmente ótima.

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

Os caminhos padrão são relativos ao repositório; a execução pode começar em
qualquer diretório. Há opções --data-dir, --k-values e --candidates.
O script de figuras gera curvas K=10 a160 em passos10 e mapas do cenário70.

## Métricas e atribuição

Todas as métricas operacionais usam distância de Haversine à instalação mais
próxima. Atribuir 100% dos pedidos é construção dessa avaliação; cobertura em
3/5/10km é a fração de pedidos dentro de cada raio.
Mediana/P95/P99 são ponderados pelos pedidos, com interpolação linear sobre
np.repeat(distâncias,n_pedidos). Os percentis não ponderados por CEP são
exportados separadamente. P95/P99 são indicadores posteriores à formação,
sem restrição de distância máxima implementada.

Os rótulos nativos dos grupos também são exportados. A área de convex hull
usa os grupos nativos, projeção EPSG:31983 e inclui área zero para grupos com
menos de três pontos. É descrição espacial, não área real de atendimento.
Ward/KMeans ajustam coordenadas angulares euclidianas; complete/average usam
Haversine. A avaliação comum usa Haversine para todos.

## Resultados em K=70

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
