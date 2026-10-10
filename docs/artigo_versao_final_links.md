# Artigo — versão final e trilha de verificação

A versão final preserva o conteúdo científico da v23 e revisa apenas a redação:
termos unificados, definições no ponto de uso, Quadro 1 de termos e notação,
citação de todas as figuras e tabelas na ordem de numeração, legendas que explicam
os rótulos internos das figuras e resumos mais diretos.

- [Google Docs da versão final](https://docs.google.com/document/d/1A--MXil_nldLSVhwtTSnesUt33assTWEwxuh4byMl1Q/edit)
- [Código científico congelado da extensão v23](https://github.com/brunomoraes87/pickup-points-rmrj/tree/952ee3a26e4b47a69ca2491b2420507df8ed8498)
- [PR de revisão](https://github.com/brunomoraes87/pickup-points-rmrj/pull/3)

O acesso ao Google Docs segue as permissões do proprietário. Este arquivo não
altera o compartilhamento do documento. Na conferência da conversão, os 175
parágrafos e as 1.209 células de tabela do DOCX aparecem idênticos no Google Docs.

Arquivos locais da entrega: `Artigo_versao_final.docx`, `Artigo_versao_final.pdf`
e `Artigo_versao_final_marcas_de_revisao.docx`, em
`C:\Users\brunmartins\revisao_artigo_pickup_points\versoes_artigo\08_Versao_final`.

| Artefato | SHA-256 |
|---|---|
| DOCX | ca02416ea591c95ecf9baf760d7c770b660777d3c811682916c44f170b78e7a8 |
| PDF, 43 páginas | dfda5c1e521bb6fad0291487add8afb9e8d1479aaaab3392093c53a5c65222da |
| DOCX com marcas de revisão desde a v24 | 4243134051e9524cbe3473e739bd4911cad4959bd10775dab30174277291a894 |

O [guia de figuras e tabelas](figuras_e_tabelas_do_artigo.md) liga cada figura e
tabela do artigo ao arquivo, ao script e aos dados de origem neste repositório.

Os valores citados no texto vêm dos artefatos congelados deste repositório.
A comparação do MCLP exato com K=14 e do Greedy Adding com K=15, em R=10 km,
usa `data/v22_verified/exact/exact_results.csv`. A escolha de T nas alternativas
exatas segue `data/v23_verified/profiles/LEIA_ME.txt`.

## Conferência dos números

`conferencia_numeros_versao_final.csv` lista 946 itens do artigo final:
células de todas as tabelas, números do texto, comparações qualitativas, as
cinco figuras e os caminhos de arquivo citados. Cada item indica o arquivo e o
campo de origem no commit 952ee3a. Os 943 itens com fonte no repositório
coincidem com ela; nenhum diverge.

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
