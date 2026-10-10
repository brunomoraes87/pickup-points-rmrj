
"""Controlled K=70 sensitivity: identical methods/candidates, before/after cleaning."""
from pathlib import Path
import hashlib,json
import pandas as pd
from methods import (evaluate,method_agglomerative,method_kmeans_weighted,
                     method_pmedian_heuristic,method_mclp_heuristic)
REPO=Path(__file__).resolve().parents[1]
def main():
    inputs={
        "before_cleaning":REPO/"data/quality/baseline_demanda_f9956c3.csv",
        "after_cleaning":REPO/"data/demanda_por_cep.csv"}
    rows=[]
    for phase,path in inputs.items():
        df=pd.read_csv(path).reset_index(drop=True)
        top=df.nlargest(300,"n_pedidos").index.values
        configs=[
            ("KMeans-weighted",method_kmeans_weighted(df,n_clusters=70)),
            ("Agglomerative-ward",method_agglomerative(df,n_clusters=70,linkage="ward")),
            ("Agglomerative-complete",method_agglomerative(df,n_clusters=70,linkage="complete")),
            ("Agglomerative-average",method_agglomerative(df,n_clusters=70,linkage="average")),
            ("P-Median",method_pmedian_heuristic(df,p=70,candidates_idx=top)),
            ("MCLP-R3km",method_mclp_heuristic(df,p=70,radius_km=3,candidates_idx=top))]
        for method,(labels,centers,runtime) in configs:
            rows.append({"phase":phase,"method":method,"K_target":70,
                         "total_orders":int(df.n_pedidos.sum()),"n_prefixes":len(df),
                         **evaluate(df,labels,centers)})
    result=pd.DataFrame(rows)
    result.to_csv(REPO/"data/cleaning_sensitivity_K70.csv",index=False)
    metadata={"baseline_commit":"f9956c30c1ca8a5c9bf638cec0dfc9e2d5fdecd9",
              "K":70,"candidate_count":300,
              "input_sha256":{phase:hashlib.sha256(path.read_bytes()).hexdigest() for phase,path in inputs.items()},
              "policy":"Only data preparation differs. Same six method implementations, candidate ranking, seed42 and order-weighted nearest-facility metrics."}
    (REPO/"data/quality/cleaning_sensitivity_metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(result[["phase","method","weighted_avg_distance_km","max_distance_km"]].to_string(index=False))
if __name__=="__main__":main()
