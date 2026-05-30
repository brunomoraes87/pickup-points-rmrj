# Localização de pontos de retirada na Região Metropolitana do Rio de Janeiro

> Material suplementar do artigo *"Decisão de localização de pontos de retirada em redes de e-commerce: análise comparativa de métodos algorítmicos aplicada à Região Metropolitana do Rio de Janeiro"*

Comparação empírica de quatro métodos algorítmicos para o problema de localização de pontos de retirada em e-commerce, utilizando 9.692 pedidos entregues na Região Metropolitana do Rio de Janeiro extraídos do dataset público Olist (2016–2018).

## Métodos comparados

1. **Agglomerative Hierarchical Clustering** — três variantes de *linkage* (average, complete, Ward)
2. **DBSCAN** — clustering por densidade
3. **K-Means demand-weighted** — baseline
4. **P-Median** — otimização via heurística de troca de Teitz & Bart (1968)

## Estrutura do repositório

```
.
├── data/                    # Dados processados (Olist filtrado para RMRJ)
│   ├── demanda_por_cep.csv      # 829 pontos de demanda agregados
│   ├── pedidos_rmrj_geo.csv     # 9.692 pedidos com geolocalização
│   ├── clientes_rmrj.csv        # 10.107 clientes na RMRJ
│   ├── geo_rmrj_agg.csv         # Coordenadas por CEP agregadas
│   ├── results_full.csv         # Todas as 38 configurações experimentais
│   └── results_clustering.csv   # Subconjunto: métodos de clustering
├── scripts/
│   └── methods.py           # Implementação dos quatro métodos + métricas
├── figures/                 # Figuras geradas
│   ├── 01_exploracao_demanda.png
│   ├── 02_cobertura_vs_K.png
│   ├── 03_distancia_vs_K.png
│   ├── 04_mapas_K15.png
│   └── 05_tradeoff_cobertura.png
└── notebooks/               # Notebooks de exploração (opcional)
```

## Reproduzir os experimentos

### Pré-requisitos

```bash
pip install -r requirements.txt
```

### Dataset original

O dataset Olist completo (não incluído neste repositório por tamanho — ~85 MB) deve ser baixado em [Kaggle: Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

Os dados processados (filtrados para a RMRJ e agregados por CEP) estão disponíveis em `data/`.

### Rodar os experimentos

```python
import pandas as pd
import sys
sys.path.insert(0, 'scripts')
from methods import (method_agglomerative, method_dbscan,
                     method_kmeans_weighted, method_pmedian_heuristic,
                     evaluate)

df = pd.read_csv('data/demanda_por_cep.csv')
TOP = df.nlargest(100, 'n_pedidos').index.values

# Exemplo: Agglomerative com K=20
labels, centers, rt = method_agglomerative(df, n_clusters=20, linkage='ward')
metrics = evaluate(df, labels, centers)
print(metrics)
```

## Principais resultados (configuração K=20)

| Método | d̄w (km) | Cob. 3km | Cob. 5km | Cob. 10km |
|---|---|---|---|---|
| K-Means ponderado | **4,01** | 39,9% | 73,1% | **97,2%** |
| Agglomerative-Ward | 4,49 | 27,8% | 66,2% | 96,0% |
| P-Median | 4,56 | **61,4%** | **77,6%** | 90,1% |
| Agglomerative-complete | 5,12 | 22,5% | 53,0% | 95,3% |
| Agglomerative-average | 6,77 | 14,3% | 29,7% | 88,1% |

## Citação

```bibtex
@article{moraes2025pickup,
  title={Decisão de localização de pontos de retirada em redes de e-commerce:
         análise comparativa de métodos algorítmicos aplicada à
         Região Metropolitana do Rio de Janeiro},
  author={Moraes, Bruno M.},
  journal={Revista de Gestão e Secretariado},
  year={2025},
  note={Submetido}
}
```

## Licença

[MIT License](LICENSE) — para o código.
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — para os dados processados.

Dataset original Olist está sob a licença [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — verifique no Kaggle.

## Contato

Bruno M. Moraes — _[seu e-mail acadêmico aqui]_
