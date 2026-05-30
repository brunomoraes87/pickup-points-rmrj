# Localização de pontos de retirada na Região Metropolitana do Rio de Janeiro

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)

## Status

Material em desenvolvimento. O trabalho associado está em fase de preparação. Comentários e contribuições são bem-vindos via Issues.

> Código, dados processados e figuras associados ao trabalho em desenvolvimento sobre localização de pontos de retirada em redes de e-commerce.

Comparação empírica de quatro métodos algorítmicos para o problema de localização de pontos de retirada em e-commerce, utilizando 9.692 pedidos entregues na Região Metropolitana do Rio de Janeiro extraídos do dataset público Olist (2016–2018).

## Métodos comparados

1. **Agglomerative Hierarchical Clustering** — três variantes de *linkage* (average, complete, Ward)
2. **DBSCAN** — clustering por densidade
3. **K-Means demand-weighted** — baseline
4. **P-Median** — otimização via heurística de troca de Teitz & Bart (1968)

## Estrutura do repositório

**`data/`** — Dados processados (Olist filtrado para RMRJ)
- `demanda_por_cep.csv` — 829 pontos de demanda agregados
- `pedidos_rmrj_geo.csv` — 9.692 pedidos com geolocalização
- `clientes_rmrj.csv` — 10.107 clientes na RMRJ
- `geo_rmrj_agg.csv` — Coordenadas por CEP agregadas
- `results_full.csv` — Todas as 38 configurações experimentais
- `results_clustering.csv` — Subconjunto: métodos de clustering

**`scripts/`** — Código-fonte
- `methods.py` — Implementação dos quatro métodos + métricas
- `01_prepare_data.py` — Filtra Olist cru para RMRJ e agrega por CEP
- `02_run_experiments.py` — Roda as 38 configurações experimentais
- `03_plot_figures.py` — Gera as 5 figuras do artigo

**`figures/`** — Figuras geradas
- `01_exploracao_demanda.png`
- `02_cobertura_vs_K.png`
- `03_distancia_vs_K.png`
- `04_mapas_K15.png`
- `05_tradeoff_cobertura.png`

**`notebooks/`**
- `example.py` — Exemplo de uso isolado

## Reproduzir os experimentos

### Pré-requisitos

```bash
pip install -r requirements.txt
```

### Pipeline completo (do zero)

O repositório segue um pipeline em 3 etapas. Cada script é executado a partir da pasta `scripts/`.

**Etapa 1 — Preparação dos dados** (opcional, já incluído em `data/`)

Filtra o Olist cru para a RMRJ e agrega a demanda por CEP.

```bash
# Baixar os 4 CSVs do Kaggle e colocar em ../olist_raw/
cd scripts
python 01_prepare_data.py
# Gera: data/clientes_rmrj.csv, geo_rmrj_agg.csv, pedidos_rmrj_geo.csv, demanda_por_cep.csv
```

**Etapa 2 — Rodar os 38 experimentos**

```bash
cd scripts
python 02_run_experiments.py
# Gera: data/results_full.csv
```

**Etapa 3 — Gerar as 5 figuras**

```bash
cd scripts
python 03_plot_figures.py
# Gera: figures/01...05_*.png
```

### Uso rápido — exemplo isolado

Para rodar os 4 métodos em uma configuração específica, veja `notebooks/example.py`:

```python
import pandas as pd
import sys
sys.path.insert(0, 'scripts')
from methods import method_agglomerative, evaluate

df = pd.read_csv('data/demanda_por_cep.csv')
labels, centers, rt = method_agglomerative(df, n_clusters=20, linkage='ward')
print(evaluate(df, labels, centers))
```

### Dataset original

O dataset Olist completo (não incluído neste repositório por tamanho — ~85 MB) deve ser baixado em [Kaggle: Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

Os dados processados (filtrados para a RMRJ e agregados por CEP) já estão disponíveis em `data/`.

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
@software{moraes2026pickup,
  title  = {Pickup Points RMRJ: comparação de métodos algorítmicos
            para localização de pontos de retirada (material e código)},
  author = {Moraes, Bruno M.},
  year   = {2026},
  url    = {https://github.com/brunomoraes87/pickup-points-rmrj}
}
```

## Licença

[MIT License](LICENSE) — para o código.
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — para os dados processados.

Dataset original Olist está sob a licença [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — verifique no Kaggle.

## Contato

Bruno M. Moraes — [@brunomoraes87](https://github.com/brunomoraes87)
