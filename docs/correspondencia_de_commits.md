# Correspondência entre os commits antigos e os atuais

Em 10/10/2026, as mensagens de todos os commits deste repositório foram traduzidas
para o português. O conteúdo de cada arquivo, em cada commit, ficou idêntico: mudaram
só as mensagens e, por isso, os identificadores. O commit e688d15 é a versão fixa
citada no artigo, com os mesmos arquivos do antigo 952ee3a.

Três registros de origem gravados dentro de arquivos verificados guardam identificadores
anteriores e não foram alterados, para não mudar esses arquivos:

- `data/v23_verified/profiles/manifest.json` e `scripts/13_certify_service_profiles_v23.py`
  registram `c202b698` como commit de origem; hoje ele é o b8a0894.
- `data/quality/cleaning_sensitivity_metadata.json` e `scripts/04_compare_cleaning.py`
  registram `f9956c3` como commit de base, que também aparece no nome de
  `data/quality/baseline_demanda_f9956c3.csv`; hoje ele é o bd3e359.

| Anterior | Atual | Mensagem |
|---|---|---|
| f9956c3 | bd3e359 | Versão inicial do projeto |
| b395d4d | fcc5a72 | Valida a geolocalização na RMRJ e reproduz a comparação comum com K=70 |
| 3078e6f | 8f82e2b | Preserva os hashes de auditoria e marca a incerteza das coordenadas derivadas |
| 3b42c1e | 5ba26fb | Seleciona a quantidade de instalações de cada método para cobertura de 95% no raio |
| f5b548b | 2b1a95a | Acrescenta referências exatas certificadas de localização finita e de proximidade obrigatória |
| 8844437 | 1228725 | Preserva as seleções principais e instrumenta as trocas equivalentes da p-mediana |
| 5ee2dc9 | 79178c9 | Acrescenta sensibilidades rastreáveis de geometria, candidatos, coortes e sementes |
| 859023d | 4cf30b9 | Acrescenta a pipeline fria da v22, a verificação independente e as figuras científicas |
| 273f846 | e66161f | Corrige os caminhos de entrada do verificador independente e a proveniência do manifesto final |
| ab2f061 | 818d17a | Valida de forma independente os manifestos nativos assinados das sensibilidades |
| c202b69 | b8a0894 | Publica os resultados verificados da v22 e as figuras de comparação exata |
| fa3f196 | 0a8786f | Integra as correções do parecer da v22 |
| 952ee3a | e688d15 | Certifica os perfis condicionais de atendimento sem alterar os ajustes principais |
| c78dbd1 | 9fa9fe2 | Liga o artigo v23 verificado e os registros da entrega |
| 6b8bad7 | d42a49a | Liga o artigo final e os registros da entrega |
| 0ad4f6e | 738330c | Liga as figuras e tabelas do artigo às suas fontes e atualiza os registros finais |
| 513d180 | f4f5d68 | Liga o artigo final no Google Docs |
| bb294ac | b19ac3d | Desenha as figuras da v22 a partir das curvas exportadas quando faltam os checkpoints |
| 8c2221a | 464ba96 | Explica como desenhar as figuras da v22 sem os checkpoints |
| 6288564 | 3a36a4c | Integra os perfis de atendimento da v23 |
| 8397591 | 760f937 | Registra os ajustes do apêndice da versão final |
| dfea230 | 505bcb1 | Integra os ajustes do apêndice da versão final |
| 98de5f6 | b9f5e8f | Orienta o leitor do artigo até os arquivos e o código |
