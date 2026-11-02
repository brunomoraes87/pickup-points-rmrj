# Análise Envoltória de Dados (DEA) das redes de pontos de retirada

Esta pasta reúne o código e os resultados de um artigo em preparação que avalia, por DEA, as redes de pontos
de retirada geradas neste repositório. Não altera nenhum arquivo do estudo original: lê apenas as saídas
verificadas em `data/`, que são as mesmas da versão científica fixa
[e688d15](https://github.com/brunomoraes87/pickup-points-rmrj/tree/e688d15cc475e58bef9128ff5bbc8fa036fe50f4).

## Desenho da análise

- **DMUs:** em cada raio de serviço (R = 3, 5 e 10 km), as seis redes dos métodos (K-Means, Ward, Complete,
  Average, p-mediana e MCLP) e as redes exatas que cumprem a mesma meta de 95% dos pedidos (9.207 de 9.691):
  cobertura parcial, cobertura parcial com proximidade obrigatória (T), p-mediana exata e MCLP exato.
  São 18, 19 e 17 DMUs, 54 no total.
- **Inputs:** número de pontos (K) e distância ao ponto mais próximo, em dois perfis: distância média
  (perfil média) e distância máxima (perfil máximo).
- **Output:** pedidos cobertos a até R km.
- **Modelo principal:** CCR orientado a inputs, forma do envelope, em duas fases (eficiência e folgas).
- **Verificações:** BCC; análise só com as seis redes dos métodos; CCR com o output fixado na meta;
  segunda fase com objetivo normalizado.
- **Verificação exploratória, não incluída no artigo:** FDH orientado a inputs.

## Arquivos

| Pasta | Arquivo | Conteúdo |
|---|---|---|
| `scripts/` | `dea_ccr_por_raio.py` | Monta as 54 DMUs a partir de `data/` e calcula o CCR de primeira fase |
| `scripts/` | `resultados_dea.py` | CCR em duas fases (eficiência, benchmarks e λ, folgas, alvos), BCC e análise só com os métodos |
| `scripts/` | `testes_robustez.py` | Output fixo na meta, segunda fase com objetivo normalizado e FDH exploratório |
| `scripts/` | `lista_redes.py` | Lista legível das 54 DMUs (separador `;` e vírgula decimal) |
| `scripts/` | `figura1_redes_5km.py`, `figura2_fronteira_5km.py`, `figura_eficiencias_perfis.py` | Figuras 1, 2 e 3 |
| `resultados/` | `redes_e_eficiencias_ccr.csv` | Inputs e output das 54 DMUs |
| `resultados/` | `resultados_dea_completos.csv` | 108 avaliações (54 DMUs × 2 perfis) |
| `resultados/` | `testes_robustez.csv` | Resultados dos testes de robustez |
| `resultados/` | `lista_de_redes_avaliadas.csv` | Lista legível das DMUs |
| `figuras/` | `figura_1_redes_5km.png`, `figura_2_fronteira_5km.png`, `figura_3_eficiencias_perfis.png` | Figuras do artigo |

No artigo, as Tabelas 1 (redes dos métodos) e 2 (composição dos grupos) saem de `redes_e_eficiencias_ccr.csv`,
e as Tabelas 3 e 4 (perfis média e máximo), de `resultados_dea_completos.csv`. Os números da Seção 5.3 saem
das colunas `h_bcc` e `h_so_metodos` desse arquivo e de `testes_robustez.csv`.

Nas colunas, `familia = PSC` identifica as redes de cobertura parcial; com `T` preenchido, são as redes com
proximidade obrigatória. `s1_objetivo_normalizado` e `s2_objetivo_normalizado` guardam folgas nas unidades
originais (pontos e km), obtidas com o objetivo normalizado.

## Reprodução

Ambiente: as bibliotecas de `requirements-reproduction.txt` (NumPy 2.5.3, pandas 3.0.1, SciPy 1.18.1,
matplotlib 3.11.2, pyproj 3.8.0, shapely 2.1.2), com Python 3.13.17; os problemas de programação linear são
resolvidos pelo HiGHS, via `scipy.optimize.linprog`. Na raiz do repositório:

```bash
python dea/scripts/dea_ccr_por_raio.py data dea/resultados/redes_e_eficiencias_ccr.csv
python dea/scripts/resultados_dea.py dea/resultados/redes_e_eficiencias_ccr.csv dea/resultados/resultados_dea_completos.csv
python dea/scripts/testes_robustez.py dea/resultados/resultados_dea_completos.csv dea/resultados/testes_robustez.csv
python dea/scripts/lista_redes.py dea/resultados/redes_e_eficiencias_ccr.csv dea/resultados/lista_de_redes_avaliadas.csv
python dea/scripts/figura1_redes_5km.py . dea/figuras/figura_1_redes_5km.png
python dea/scripts/figura2_fronteira_5km.py dea/resultados/redes_e_eficiencias_ccr.csv dea/figuras/figura_2_fronteira_5km.png
python dea/scripts/figura_eficiencias_perfis.py dea/resultados/resultados_dea_completos.csv dea/figuras/figura_3_eficiencias_perfis.png
```

Com esse ambiente, no Windows, os arquivos gerados foram idênticos, byte a byte, aos desta pasta. As figuras
usam a fonte Times New Roman; em outro sistema, podem diferir na aparência, sem mudar os dados.
