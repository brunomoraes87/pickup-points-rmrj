"""Run reproducible configurations, including a common K=70 comparison."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import MultiPoint
from methods import (EARTH_R_KM, evaluate, haversine_to_centers, method_agglomerative,
                     method_dbscan, method_kmeans_weighted, method_mclp_heuristic,
                     method_pmedian_heuristic)
REPO = Path(__file__).resolve().parents[1]
PAPER_METHODS = ["KMeans-weighted","Agglomerative-ward","Agglomerative-complete",
                 "Agglomerative-average","P-Median","MCLP-R3km"]
EPS_VALUES = [1.0,1.5,2.0,2.5,3.0,4.0,5.0,7.0]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def hull_area(points, labels, n_centers):
    if not n_centers:return float("nan")
    areas=[]
    for i in range(n_centers):
        p=points[labels==i]
        areas.append(MultiPoint(p).convex_hull.area/1e6 if len(p)>=3 else 0.)
    return float(np.mean(areas))
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=REPO/"data")
    parser.add_argument("--k-values",type=int,nargs="+",default=[5,10,15,20,25,30,70])
    parser.add_argument("--candidates",type=int,default=300)
    parser.add_argument("--pmedian-max-iter",type=int,default=100)
    args=parser.parse_args()
    path=args.data_dir/"demanda_por_cep.csv"
    df=pd.read_csv(path,dtype={"customer_zip_code_prefix":str}).reset_index(drop=True)
    if "CEP" not in df:df=df.rename(columns={"customer_zip_code_prefix":"CEP"})
    counts=df.n_pedidos.to_numpy(dtype=float)
    coords=df[["lat","lng"]].to_numpy(dtype=float)
    if not np.isfinite(counts).all() or (counts<=0).any() or (counts!=np.floor(counts)).any():
        raise ValueError("Demand must have positive integer order counts")
    if not np.isfinite(coords).all() or df.CEP.duplicated().any():
        raise ValueError("Demand coordinates must be finite and CEPs unique")
    if args.candidates<=0 or args.pmedian_max_iter<=0 or any(k<=0 for k in args.k_values):
        parser.error("Positive parameters required")
    if len(set(args.k_values))!=len(args.k_values):
        parser.error("Duplicate K values")
    top=df.nlargest(min(args.candidates,len(df)),"n_pedidos").index.values
    if max(args.k_values)>min(len(df),len(top)):
        parser.error("K exceeds the number of demand points/candidates")
    transformer=Transformer.from_crs("EPSG:4326","EPSG:31983",always_xy=True)
    x,y=transformer.transform(coords[:,1],coords[:,0])
    projected=np.column_stack([x,y])
    rows,facility_exports,assignment_exports=[],[],[]
    def record(name,k,labels,centers,runtime,**extra):
        labels=np.asarray(labels,dtype=int)
        centers=np.asarray(centers,dtype=float).reshape(-1,2)
        rows.append({"method":name,"K_target":k,"runtime_s":float(runtime),
                     "mean_convex_hull_area_km2":hull_area(projected,labels,len(centers)),
                     **evaluate(df,labels,centers),**extra})
        if k==70 and name in PAPER_METHODS:
            D=haversine_to_centers(coords[:,0],coords[:,1],centers[:,0],centers[:,1])
            nearest=D.argmin(axis=1)
            native=np.full(len(df),np.nan)
            assigned=(labels>=0)&(labels<len(centers))
            native[assigned]=D[np.flatnonzero(assigned),labels[assigned]]
            facilities=pd.DataFrame({"method":name,"facility_id":np.arange(len(centers)),
                                     "lat":centers[:,0],"lng":centers[:,1]})
            assignments=df[["CEP","lat","lng","n_pedidos"]].copy()
            assignments.insert(0,"method",name)
            assignments["native_label"]=labels
            assignments["nearest_facility"]=nearest
            assignments["distance_km"]=D[np.arange(len(df)),nearest]
            assignments["native_distance_km"]=native
            facility_exports.append(facilities);assignment_exports.append(assignments)
        print(f"{name} K={k}: {len(centers)} facilities, {runtime:.3f}s",flush=True)
    print(f"{len(df)} CEPs / {int(counts.sum())} orders / {len(top)} candidates",flush=True)
    for k in args.k_values:
        for linkage in ("average","complete","ward"):
            record(f"Agglomerative-{linkage}",k,*method_agglomerative(df,n_clusters=k,linkage=linkage))
        record("KMeans-weighted",k,*method_kmeans_weighted(df,n_clusters=k))
        record("P-Median",k,*method_pmedian_heuristic(df,p=k,candidates_idx=top,max_iter=args.pmedian_max_iter))
        for radius in (3,5,10):
            record(f"MCLP-R{radius}km",k,*method_mclp_heuristic(df,p=k,radius_km=radius,candidates_idx=top),radius_km=radius)
    for eps in EPS_VALUES:
        labels,centers,runtime,noise=method_dbscan(df,eps_km=eps,min_samples=3)
        record("DBSCAN",None,labels,centers,runtime,eps_km=eps,n_noise=noise)
    full=pd.DataFrame(rows)
    full.to_csv(args.data_dir/"results_full.csv",index=False)
    full[full.method.str.startswith("Agglomerative")|full.method.isin(["KMeans-weighted","DBSCAN"])].to_csv(args.data_dir/"results_clustering.csv",index=False)
    paper=full[full.K_target.eq(70)&full.method.isin(PAPER_METHODS)].copy()
    paper["sort"]=paper.method.map({m:i for i,m in enumerate(PAPER_METHODS)})
    paper.sort_values("sort").drop(columns="sort").to_csv(args.data_dir/"paper_table_K70.csv",index=False)
    fcols=["method","facility_id","lat","lng"]
    acols=["method","CEP","lat","lng","n_pedidos","native_label","nearest_facility","distance_km","native_distance_km"]
    (pd.concat(facility_exports,ignore_index=True) if facility_exports else pd.DataFrame(columns=fcols)).to_csv(args.data_dir/"facilities_K70.csv",index=False)
    (pd.concat(assignment_exports,ignore_index=True) if assignment_exports else pd.DataFrame(columns=acols)).to_csv(args.data_dir/"assignments_K70.csv",index=False)
    versions={"python":platform.python_version()}
    for package in ("numpy","pandas","scikit-learn","scipy","shapely","pyproj"):
        versions[package]=importlib.metadata.version(package)
    candidate_ceps=df.loc[top,"CEP"].astype(str).tolist()
    metadata={
        "created_at_utc":datetime.now(timezone.utc).isoformat(),"versions":versions,
        "n_demand_points":len(df),"total_orders":int(counts.sum()),"k_values":args.k_values,
        "seed":42,"n_init":10,"pmedian_max_iter":args.pmedian_max_iter,
        "candidate_count":len(top),"candidates_requested":args.candidates,
        "candidate_selection":"nlargest(n_pedidos), ties keep first input row",
        "candidate_indices":top.tolist(),"candidate_CEPs":candidate_ceps,
        "candidate_prefix_sha256":hashlib.sha256(json.dumps(candidate_ceps,separators=(",",":")).encode()).hexdigest(),
        "data_sha256":{path.name:sha(path)},
        "code_sha256":{p.name:sha(p) for p in (Path(__file__),REPO/"scripts/methods.py")},
        "earth_radius_km":EARTH_R_KM,"mclp_radii_km":[3,5,10],
        "dbscan_eps_km":EPS_VALUES,"dbscan_min_samples":3,
        "evaluation_assignment":"nearest facility by Haversine, including native noise",
        "native_assignment":"original labels; -1 is unassigned; reassignment counts exclude noise",
        "weighted_percentiles":"numpy.percentile linear interpolation over np.repeat(distances,n_pedidos)",
        "CEP_percentiles":"unweighted nearest distance per prefix",
        "convex_hull_area":"native labels; EPSG:31983; mean across all facilities; fewer than3points=0area",
        "facility_id_convention":"zero-based center indices",
        "runtime_s":"method fitting only; excludes metrics/exports; hardware dependent",
        "paper_methods":PAPER_METHODS}
    (args.data_dir/"experiment_metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Saved {len(full)} configurations",flush=True)
if __name__=="__main__":main()
