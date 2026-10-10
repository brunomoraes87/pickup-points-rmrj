# Artigo — versão final e trilha de verificação

A versão final preserva o conteúdo científico da v23 e revisa apenas a redação:
termos unificados, definições no ponto de uso, Quadro 1 de termos e notação,
citação de todas as figuras e tabelas na ordem de numeração, legendas que explicam
os rótulos internos das figuras e resumos mais diretos. Na revisão de 10/10/2026,
a figura e as tabelas do apêndice passaram a ter numeração própria (Figura A.1,
Tabelas A.1 e A.2), todas as partes do apêndice passaram a ser citadas no texto e o
artigo passou a citar a página principal do repositório e a versão fixa 952ee3a.
Em seguida, os caminhos de arquivo das legendas e do Apêndice A.6 viraram links para
a versão fixa, e a Disponibilidade passou a trazer o link do guia de figuras e tabelas.

- [Google Docs da versão final](https://docs.google.com/document/d/1GvZhmW-66mDRrjC3LvmnKCOZlo-fidlIEVk_apecpv8/edit)
- [Código científico congelado da extensão v23](https://github.com/brunomoraes87/pickup-points-rmrj/tree/952ee3a26e4b47a69ca2491b2420507df8ed8498)
- [PR de revisão](https://github.com/brunomoraes87/pickup-points-rmrj/pull/3)

O acesso ao Google Docs segue as permissões do proprietário. Este arquivo não
altera o compartilhamento do documento. Na conferência da conversão, os 177
parágrafos, as 1.209 células de tabela e os 63 links do DOCX aparecem idênticos no
Google Docs.

Arquivos locais da entrega: `Artigo_versao_final.docx`, `Artigo_versao_final.pdf`
e `Artigo_versao_final_marcas_de_revisao.docx`, em
`C:\Users\brunmartins\revisao_artigo_pickup_points\versoes_artigo\08_Versao_final`.

| Artefato | SHA-256 |
|---|---|
| DOCX | 0eed8f1bf2b46905d1b8ee38b40c6582739e046a44863cbbb222a4110f8638f4 |
| PDF, 43 páginas | 4a53c2ab5977b385257e25f8bb5d4d2763a8ed510dea598578393ff346c05b14 |
| DOCX com marcas de revisão desde a v24 | c098a3d4b2fe171a50c42abd8c26be2896590bb8bcf5ef410dd949a6c63dbb0e |

O [guia de figuras e tabelas](figuras_e_tabelas_do_artigo.md) liga cada figura e
tabela do artigo ao arquivo, ao script, aos dados de origem e às funções de cálculo
neste repositório.

Os valores citados no texto vêm dos artefatos congelados deste repositório.
A comparação do MCLP exato com K=14 e do Greedy Adding com K=15, em R=10 km,
usa `data/v22_verified/exact/exact_results.csv`. A escolha de T nas alternativas
exatas segue `data/v23_verified/profiles/LEIA_ME.txt`.

## Conferência dos números

`conferencia_numeros_versao_final.csv` lista 1.012 itens do artigo final:
células de todas as tabelas, números do texto, comparações qualitativas, as
cinco figuras, os caminhos de arquivo citados, a correspondência entre as
legendas das figuras, a tabela do Apêndice A.6 e os arquivos do repositório, e os
50 links de caminhos, cada um conferido contra o arquivo que abre. Cada item indica
o arquivo e o campo de origem: no commit 952ee3a ou, para o guia, no `main`. Os
1.009 itens com fonte no repositório coincidem com ela; nenhum diverge.

Três informações do texto não estão no repositório:

- HiGHS 1.12.0: o repositório registra o SciPy 1.18.1, que incorpora essa versão do HiGHS.
- Travessão e Tocos como distritos de Campos dos Goytacazes: vem dos rótulos de
  cidade da base pública da Olist e da malha do IBGE; o repositório registra a
  divisão dos registros desses prefixos em `omission_hypotheses.csv`.
- Processador, núcleos e memória do computador usado: registro local da execução.

As figuras do artigo correspondem, com o redimensionamento da edição, aos PNG de
`figures/v22_verified/` e `figures/v23_verified/`.

A publicação destes links é posterior ao commit científico congelado. Este
registro não modifica modelos, entradas, certificados, métricas ou figuras:
as imagens do artigo são as geradas por `scripts/15geracao_figuras_verificadas.py`
e pelas etapas anteriores, sem edição manual.
