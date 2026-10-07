# Localização de pontos de retirada na RMRJ — v22

Código da revisão do manuscrito de Bruno M. Moraes. A condição principal conserva
a coorte de 9.691 pedidos entregues, representados por 828 centroides de prefixo
postal, e os ajustes da versão anterior. Os resultados adicionais são separados
em benchmarks exatos e análises de sensibilidade.

## Pergunta e limites

A busca encontra o primeiro K inteiro viável em cada implementação: pelo menos
95% da demanda, ponderada por pedidos, tem seu **centroide de prefixo** a até
R=3, 5 ou 10 km da instalação mais próxima. Isso exige 9.207 pedidos nesta
coorte. Cada inteiro menor é testado; não se presume monotonicidade. K é o número
de instalações. A demanda é medida em pedidos, sob a hipótese de uma viagem
de retirada por pedido; não se confunde com os 9.347 compradores únicos.

São seis configurações: K-Means ponderado, Ward, Complete, Average, p-mediana
por construção e trocas e MCLP por Greedy Adding. DBSCAN é exploração anterior,
sem protocolo comparável de busca de parâmetros e atendimento do ruído.
O requisito P95 é externo ao objetivo dos métodos: não modifica ou remove seus
grupos de formação. Toda demanda participa da avaliação pela instalação mais
próxima. Não se demonstra mínimo econômico, capacidade, viabilidade de imóvel,
atendimento a endereço individual ou distância viária.

## Condição principal

Haversine usa raio terrestre de 6.371,0088 km. K-Means/Ward ajustam coordenadas
angulares; Complete/Average usam matriz Haversine. Os agrupamentos hierárquicos
são formados sem pesos, com centros posteriormente ponderados pelos pedidos.

K-Means: sementes 42, 0, 1, 2 e 3; n_init=10; init='k-means++';
algorithm='lloyd'; tol=1e-4; max_iter=300. A meta deve ser cumprida nas cinco
sementes no mesmo K. A semente 42 representa a rede mostrada. Exportam-se
intervalos e verificações adicionais com 30 sementes; não são garantia
probabilística. O scikit-learn implementa greedy k-means++, sem transferência
automática de garantias teóricas à busca do requisito de serviço.

P-mediana/MCLP restringem a condição principal aos 300 prefixos de maior demanda,
com desempate pelo prefixo crescente, mantendo os 828 na avaliação. A restrição
é exploratória: nenhum cadastro de imóveis comerciais a valida. O teto em
3 km é 9.079 pedidos; inverter o desempate aumenta para 9.125, ainda insuficiente.
Existe uma seleção específica de 300 entre 825 centroides internos cobrindo toda
a demanda; a afirmação não vale para qualquer conjunto de 300.

P-mediana: construção gulosa própria, trocas inspiradas em Teitz–Bart,
primeira melhora e limite de 100 passadas. Exportam-se passadas, trocas,
convergência e motivo do término. A otimização dos caches preserva os ajustes,
verificada nos 145 checkpoints reais e em instâncias sintéticas. MCLP usa
trajetórias de Greedy Adding, com orçamento de até K instalações. Os tempos
excluem matriz compartilhada, avaliação e exportação; ajuste, trajetória e busca
completa são distintos. As heurísticas não têm certificado de ótimo.

## Dados e saneamento

Verificam-se chaves e junções, coordenadas dos prefixos demandados, decisões
explícitas de revisão e conservação de demanda antes da média por prefixo.
Repetições permanecem na condição principal, com sensibilidades separadas.
Os 22 municípios da LC 184/2018 são uma delimitação analítica retrospectiva
dos pedidos de 2016–2018: a lei entrou em vigor após as compras, e Petrópolis
não integrava a composição anterior de 21 municípios.

O GeoJSON baixado com parametro periodo=2022 é byte a byte igual à malha
versionada (SHA256 em data/geography/scope.json). A união é administrativa,
**não uma máscara certificada de terra seca ou água**. Instalações externas
são sinalizadas; estar dentro não comprova acesso, imóvel ou ausência de barreira.
Segmentos externos são indicadores geométricos, não trajetos sobre água ou vias.

Os 108 prefixos com algum registro além de 20 km permanecem como incerteza;
o indicador não comprova endereço incorreto. Redistribuir pesos uniformemente
pelos registros é hipótese de sensibilidade, pois não há coordenada individual
de cada pedido. D16/D22 são inclusões hipotéticas, não recuperações confirmadas;
município inferido é exportado separadamente do município cadastral.

Olist: CC BY-NC-SA 4.0. A licença MIT do código não substitui a dos dados.
Metadados Kaggle consultados em 07/10/2026 indicam atualização em 01/10/2021;
os hashes identificam a cópia local, sem atribuir versão remota não comprovada.

## Reprodução offline completa

Use Python 3.12.14 e os pacotes fixados. Instalar dependências ou obter CSVs é
ação prévia do usuário; o pipeline não faz downloads.

```text
python -m pip install -r requirements-test.txt
python scripts/run_pipeline_v22.py --raw-dir /caminho/Originais --work-dir /caminho/novo_run
```

`--work-dir` deve não existir. A execução fria fixa controles de threads em 1,
verifica versões e executa, em ordem:

| Etapa | Função |
|---|---|
| pytest | Testes anteriores e novas invariantes/instâncias de força bruta |
| 01_prepare_data.py | Junções, revisão geográfica e demanda processada |
| 05_select_service_k.py | Busca inteira principal e J828 em 3 km |
| 07_run_exact_benchmarks.py | MILPs finitos, p-mediana e proximidade |
| 08_run_sensitivities.py | Geometria, métricas, candidatos, coortes e sementes |
| 09_plot_v22.py | Figuras, municípios, máscara, curvas e fronteiras observadas |
| 10_verify_v22_independent.py | Recomputação sem importar módulos do repositório |
| 11_export_paper_values.py | Catálogo de valores do manuscrito a partir dos resultados |

Cada etapa tem log, comando, tempo e código de saída. Os arquivos originais
são apenas lidos e seus hashes conferidos antes/depois. Não há push, PR ou
escrita em Google Docs. Saídas: processed/, results/main/, results/exact/,
results/sensitivity/, figures/ e verification/. Checkpoints e geolocation_audit
ficam fora do Git, mas são integralmente gerados pelo código.

Scripts históricos 02–04 e 06 permanecem para orçamento fixo e figuras
anteriores; não substituem a pipeline v22.

## Benchmarks e sensibilidades

Cobertura parcial minimiza instalações para uma fração de demanda. MCLP exato
maximiza demanda coberta para K fixo. P-mediana exata minimiza distância
ponderada para K fixo. Proximidade obrigatória exige cada centroide a até T,
inclusive a cauda. SciPy optimize.milp/HiGHS executa os modelos, sem PuLP ou
download de solver. Exportam-se status, primal, dual, gap e validação.
Ótimo vale no conjunto candidato finito, sem prova de ótimo contínuo. Soluções
ótimas distintas podem ter perfis de distância e municípios diferentes.

Variantes: WGS84 apenas na avaliação; WGS84 no ajuste quando compatível;
mediana por coordenada; remoção de repetições completas; EPSG:31983 com
transformação inversa dos centros e com partições projetadas/centros angulares;
J828/J825; desempate inverso; D16/D22 e pares com candidatos principais fixos.
Fit_metric e evaluation_metric distinguem cada protocolo. Intervalos descritivos
de K sobrepostos não fundamentam ordenação robusta nesses testes; não equivalem
a teste estatístico de indistinguibilidade. Pareto é não dominância entre redes
calculadas no mesmo espaço candidato, não uma fronteira global certificada.

## Manuscrito e auditoria

Os números científicos são gerados dos CSVs/JSONs. O manifesto local
Auditoria_v22/numeros_texto_v22.json registra fonte, coluna, filtro e
arredondamento. A checagem extrai números de parágrafos, tabelas, três resumos
e legendas. Anos bibliográficos, parâmetros e numeração estrutural têm fontes
de metadados separadas. A auditoria registra leitura integral das referências,
duas execuções frias, hashes, diferenças e inspeção visual de todas as páginas.
O DOCX/PDF final permanece na pasta de versões do artigo.

## Saídas verificadas para revisão do artigo v22

`data/v22_verified/` e `figures/v22_verified/` contêm cópias dos CSVs/JSONs e
figuras da reprodução A concluída, com os metadados originais de proveniência.
Os caminhos locais nesses metadados identificam a execução; uma nova reprodução
usa seu próprio `--work-dir`. Microdados por pedido, caches e PDFs acadêmicos
permanecem no material local. A cópia integral dos CSVs públicos Olist é lida em
`02_Versao_revisada/Dados_Olist/Originais` e seus hashes são conferidos.

As reproduções A/B partiram do arquivo Git 859023d9, com diretórios de saída
vazios. A etapa de sensibilidades foi interrompida e retomada apenas com seus
próprios checkpoints. O verificador foi corrigido instrumentalmente no commit
273f846 para resolver as chaves canônicas pelos caminhos de entrada registrados;
o commit ab2f061 distingue ainda o manifesto nativo assinado do lote consolidado,
sem aceitar hashes divergentes. Os algoritmos científicos congelados permaneceram
intactos. As tentativas FAILED do verificador foram preservadas. Não são execuções
ininterruptas, e os valores de tempo incluem essa circunstância quando indicado.
A auditoria local registra a comparação A/B e o SHA de cada versão.

Os três overlays de referências exatas são gerados separadamente:

```text
python scripts/12_plot_exact_overlays_v22.py --scientific-root /caminho/novo_run --out-dir /caminho/overlays
```

A verificação independente usa o mesmo SciPy/HiGHS, não um segundo solver.
A união dos municípios também não certifica terra seca ou acesso comercial.
O conjunto J300 é uma condição exploratória preservada, acompanhado de
sensibilidades; não foi transformado em cadastro de locais elegíveis.

## V23: perfis de atendimento e alternativas certificadas

A v23 preserva os ajustes, a coorte e os cenários principais da v22. A conclusão
passa a distinguir prioridades: quantidade de instalações, deslocamento médio,
pior caso/cauda e atendimento municipal. As alternativas abaixo foram escolhidas
após o parecer, para verificar os perfis observados; não são pré-registro.

`data/v23_verified/profiles/` contém 17 modelos de cobertura parcial em J825,
com proximidade obrigatória opcional, e a comparação com redes congeladas.
São exportados vetores primais y/z, coordenadas, índices, atribuições, cobertura
municipal, status, limite dual e gap. Todos os 17 casos tiveram gap zero; a
verificação separada recalculou 38 redes e 2.174 checagens, sem falhas.

Os perfis de distância e de atendimento municipal pertencem a um ótimo de
quantidade encontrado. Não são objetivos otimizados nem perfis únicos.
Uma melhora em K e máximo pode piorar média, P99 ou municípios. Os exemplos
MCLP J300 em R5/K39 e R10/K14 também permitem verificar melhorias em relação
ao Greedy Adding sem alterar o conjunto candidato. Grades internas fornecem
limites de quantidade para cobertura; esses limites não preservam os demais
indicadores das redes de agrupamento.

Com o ambiente fixado em `requirements-test.txt`, verificar as saídas entregues:

```text
python -m pytest -q
python scripts/14_verify_service_profiles_v23.py --profiles data/v23_verified/profiles --repo-root . --report verification_profiles_v23.json
```

Gerar novos casos em um diretório vazio e recalculá-los:

```text
python scripts/13_certify_service_profiles_v23.py --repo-root . --output novo_experimento_perfis
python scripts/14_verify_service_profiles_v23.py --profiles novo_experimento_perfis --repo-root . --report nova_verificacao_perfis.json
```

As figuras em `figures/v23_verified/` são produzidas por
`scripts/15geracao_figuras_verificadas.py` a partir dos artefatos congelados.
A projeção EPSG:31983 é usada somente na exibição dos novos mapas; as distâncias
de serviço permanecem Haversine. Linhas diretas não são percursos viários, e
a união administrativa não valida imóveis ou acesso.

Validação desta extensão: 78 testes e 230 subtestes; 17 certificados; verificador
independente das métricas/primal com 2.174 checagens; 20 checagens dos valores
plotados. HiGHS incorporado no SciPy fornece os limites de optimalidade; não
há validação por segundo backend.

A v23 não repete integralmente o pipeline principal. Reutiliza a evidência A/B
congelada da v22 e conserva os módulos científicos principais por SHA. Os
metadados preservam a distinção entre produtor 859023d9, verificador ab2f061
e entrega c202b698. O novo commit registra a extensão certificada. Tempos são
observações de execução, e não resultados cuja identidade entre máquinas se
exige. A análise D22 é um teste de estresse cadastral, sem recuperação validada
dos pedidos empatados; a coorte principal permanece igual.

O [Google Docs da v23 e os identificadores da entrega](docs/artigo_v23_links.md)
estão registrados separadamente do commit científico congelado.
