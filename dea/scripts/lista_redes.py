"""Listagem legível das redes avaliadas na DEA (CSV com separador ';' e vírgula decimal),
a partir de dea/resultados/redes_e_eficiencias_ccr.csv.
Uso (na raiz do repositório): python dea/scripts/lista_redes.py dea/resultados/redes_e_eficiencias_ccr.csv dea/resultados/lista_de_redes_avaliadas.csv
"""
import sys

import pandas as pd

d = pd.read_csv(sys.argv[1])
modelo = {("heurística", "K-Means"): "K-Means (agrupamento)", ("heurística", "Ward"): "Ward (agrupamento)",
          ("heurística", "Complete"): "Complete (agrupamento)", ("heurística", "Average"): "Average (agrupamento)",
          ("heurística", "p-mediana"): "p-mediana (heurística)", ("heurística", "MCLP"): "MCLP (heurística)",
          ("exata", "p-mediana"): "p-mediana exata", ("exata", "MCLP"): "MCLP exato",
          ("exata", "PSC"): "cobertura parcial"}
d["Modelo"] = [modelo[(t, f)] + (" com proximidade obrigatória" if pd.notna(T) else "")
               for t, f, T in zip(d.tipo, d.familia, d["T"])]
d["Papel na DEA"] = d.tipo.map({"heurística": "rede avaliada (método)", "exata": "gabarito (rede exata)"})
d["Lista de candidatos"] = d.conjunto.replace({"centros calculados": "livre (centro do grupo)"})
t = pd.DataFrame({
    "Raio (km)": d.R.astype(int), "Papel na DEA": d["Papel na DEA"], "Modelo": d.Modelo,
    "Lista de candidatos": d["Lista de candidatos"], "T (km)": d["T"], "Agências (K)": d.K.astype(int),
    "Distância média (km)": d.media.round(2), "Distância máxima (km)": d.maximo.round(2),
    "Pedidos cobertos": d.cob.astype(int), "% cobertos": (100 * d.cob / 9691).round(1)})
t = t.sort_values(["Raio (km)", "Papel na DEA", "Agências (K)"], ascending=[True, False, True]).reset_index(drop=True)
t.insert(0, "Nº", range(1, len(t) + 1))
# CSV no padrão do Excel em português (";" e vírgula decimal), com BOM para abrir com acentos
t.to_csv(sys.argv[2], sep=";", decimal=",", index=False, encoding="utf-8-sig")
print(t.to_string(index=False))
