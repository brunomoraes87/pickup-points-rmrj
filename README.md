# Localização de pontos de retirada na Região Metropolitana do Rio de Janeiro

> Material suplementar do artigo *"Decisão de localização de pontos de retirada em redes de e-commerce: análise comparativa de métodos algorítmicos aplicada à Região Metropolitana do Rio de Janeiro"*

Comparação empírica de **sete paradigmas algorítmicos** para o problema de localização de pontos de retirada em e-commerce, utilizando 9.692 pedidos entregues na Região Metropolitana do Rio de Janeiro (RMRJ) extraídos do dataset público Olist (2016–2018). O estudo adota duas premissas operacionais explícitas — cobertura universal e minimização do deslocamento — e fundamenta a escolha do número de centroides nas métricas operacionais do problema.

## Métodos comparados

1. **Agglomerative Hierarchical Clustering** — três variantes de *linkage* (average, complete, Ward)
2. **DBSCAN** — clustering por densidade
3. **K-Means demand-weighted** — K-Means com ponderação por demanda
4. **P-Median** (Hakimi, 1964) — heurística de troca de Teitz & Bart (1968)
5. **MCLP** (Church & ReVelle, 1974) — Maximal Covering Location Problem, heurística gulosa

## Estrutura do repositório

```
.
├── data/                              # Dados processados (Olist filtrado para RMRJ)
│   ├── demanda_por_cep.csv            # 829 pontos de demanda agregados
│   ├── pedidos_rmrj_geo.csv           # 9.692 pedidos com geolocalização
│   ├── clientes_rmrj.csv              # Clientes RMRJ
│   ├── geo_rmrj_agg.csv               # Coordenadas por CEP agregadas
│   ├── results_full.csv               # Todas as configurações experimentais
│   └── results_clustering.csv         # Subconjunto: métodos de clustering
├── scripts/
│   ├── 01_prepare_data.py             # Pipeline: Olist → RMRJ filtrado
│   ├── 02_run_experiments.py          # Roda todas as configurações
│   ├── 03_plot_figures.py             # Gera todas as figuras
│   └── methods.py                     # Implementação dos métodos + métricas
├── figures/
│   ├── 01_exploracao_demanda.png      # Distribuição da demanda na RMRJ
│   ├── 02_cobertura_vs_K.png          # Cobertura efetiva em função de K
│   ├── 03_distancia_vs_K.png          # Distância média ponderada em função de K
│   ├── 04_mapas_K15.png               # Mapas espaciais em K=15 (exploratório)
│   ├── 04_mapas_K70.png               # Mapas espaciais em K=70 (Figura 3 do paper)
│   ├── 05_tradeoff_cobertura.png      # Trade-off cobertura × distância
│   ├── 07_saturacao_K70.png           # Saturação K=70 (Figura 1 do paper)
│   └── 08_dominancia_linkages.png     # Dominância intra-paradigma (Figura 2 do paper)
└── notebooks/
    └── example.py                     # Exemplo de uso da API
```

## Reproduzir os experimentos

### Pré-requisitos

```bash
pip install -r requirements.txt
```

### Dataset original

O dataset Olist completo (~85 MB) deve ser baixado em [Kaggle: Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Os dados já processados (filtrados para a RMRJ e agregados por CEP) estão disponíveis em `data/`.

### Pipeline completo

```bash
# 1. Preparar dataset (Olist → RMRJ → CEPs agregados)
python scripts/01_prepare_data.py

# 2. Rodar todas as configurações experimentais
python scripts/02_run_experiments.py

# 3. Gerar todas as figuras do paper
python scripts/03_plot_figures.py
```

### Exemplo de uso da API

```python
import pandas as pd
import sys
sys.path.insert(0, 'scripts')
from methods import (method_agglomerative, method_dbscan,
                     method_kmeans_weighted, method_pmedian_heuristic,
                     method_mclp_heuristic, evaluate)

df = pd.read_csv('data/demanda_por_cep.csv')
TOP = df.nlargest(100, 'n_pedidos').index.values

# P-Median com K=70 (configuração final do paper)
labels, centers, rt = method_pmedian_heuristic(df, p=70, candidates_idx=TOP)
metrics = evaluate(df, labels, centers)
print(metrics)
```

## Principais resultados (configuração K=70)

Comparação *apples-to-apples* dos métodos em K=70 (Tabela 1 do paper):

| Método | d̄w (km) | Cob. 3km | Cob. 5km | Cob. 10km | Área (km²) |
|---|---|---|---|---|---|
| K-Means weighted | 1,49 | 91,2% | 99,1% | 100,0% | 17,28 |
| Agglomerative-Ward | 1,79 | 90,9% | 98,9% | 100,0% | **14,04** |
| Agglomerative-complete | 1,92 | 85,4% | 99,8% | 100,0% | 14,40 |
| Agglomerative-average | 2,18 | 75,0% | 94,5% | 100,0% | 15,82 |
| P-Median | **1,46** | 88,8% | 96,2% | 99,3% | 21,46 |
| MCLP — R=3 km | 1,76 | **92,6%** | 96,4% | 99,4% | 6,84 |

Distribuição completa de distâncias — a importância da cauda (Tabela 2 do paper):

| Método | mediana | P95 | P99 | máximo |
|---|---|---|---|---|
| K-Means weighted | 1,26 | 3,33 | 4,82 | 15,14 |
| Agglomerative-Ward | 1,73 | 3,33 | 5,15 | 8,48 |
| Agglomerative-complete | 1,86 | 3,83 | **4,65** | **6,26** |
| Agglomerative-average | 2,14 | 4,05 | 4,52 | 6,79 |
| P-Median | **1,06** | 4,31 | 8,60 | 160,78 |
| MCLP — R=3 km | 1,59 | 4,28 | 8,60 | 160,78 |

Três finalistas emergem com filosofias gerenciais distintas: **K-Means weighted** (cliente médio), **Agglomerative-Ward** (consistência) e **Agglomerative-complete** (controle democrático). A recomendação final depende do SLA contratual da rede.

## Citação

```bibtex
@article{moraes2026pickup,
  title  = {Decisão de localização de pontos de retirada em redes de e-commerce:
            análise comparativa de métodos algorítmicos aplicada à
            Região Metropolitana do Rio de Janeiro},
  author = {Moraes, Bruno M.},
  journal= {Revista de Gestão e Secretariado},
  year   = {2026},
  note   = {Submetido}
}
```

## Licença

- **Código**: [MIT License](LICENSE)
- **Dados processados**: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Dataset original Olist**: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — verifique no Kaggle.

## Contato

Bruno M. Moraes — Pesquisador Independente, Niterói, RJ, Brasil
- ORCID: [0009-0007-3756-2081](https://orcid.org/0009-0007-3756-2081)
- Lattes: [5771797960530611](http://lattes.cnpq.br/5771797960530611)
- LinkedIn: [brunom-moraes](https://www.linkedin.com/in/brunom-moraes/)
