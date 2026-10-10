"""Figures and municipal diagnostics for the service-constrained search."""
import argparse, colorsys, json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

REPO=Path(__file__).resolve().parents[1]
METHODS=["KMeans-weighted","Agglomerative-ward","Agglomerative-complete",
         "Agglomerative-average","P-Median","MCLP"]
LABELS=dict(zip(METHODS,["K-Means","Ward","Complete","Average","P-mediana","MCLP"]))
COLORS=["#238b45","#2171b5","#756bb1","#8c564b","#cb181d","#e6550d"]
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11})

def method_base(name):
    return "MCLP" if str(name).startswith("MCLP") else str(name)
def quantile(values,q):
    return float(np.quantile(values,q,method="inverted_cdf"))
def save(fig,path):
    fig.tight_layout()
    fig.savefig(path,dpi=170,bbox_inches="tight")
    plt.close(fig)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir",type=Path,default=REPO/"data/service_selection")
    p.add_argument("--data-dir",type=Path,default=REPO/"data")
    p.add_argument("--figures-dir",type=Path,default=REPO/"figures/service_selection")
    args=p.parse_args()
    out=args.results_dir; figs=args.figures_dir; figs.mkdir(parents=True,exist_ok=True)
    sel=pd.read_csv(out/"service_selection.csv")
    a=pd.read_csv(out/"service_assignments.csv",dtype={"CEP":str,"customer_zip_code_prefix":str})
    f=pd.read_csv(out/"service_facilities.csv")
    sel["method_base"]=sel.method.map(method_base)
    a["method_base"]=a.method.map(method_base);f["method_base"]=f.method.map(method_base)
    scopes=sel.scope.unique().tolist()
    main_scope=next(s for s in scopes if "main" in str(s) or str(s)=="principal")
    sensitivity_scope=next((s for s in scopes if s!=main_scope),None)
    viable=sel.K_selected.notna()
    def choose(method,radius,allow_sensitivity=False):
        sub=sel[(sel.scope==main_scope)&(sel.method_base==method)&(sel.radius_km==radius)&viable]
        if sub.empty and allow_sensitivity and sensitivity_scope:
            sub=sel[(sel.scope==sensitivity_scope)&(sel.method_base==method)&(sel.radius_km==radius)&viable]
        return None if sub.empty else sub.iloc[0]
    def assignment(row):
        mask=(a.scope==row.scope)&(a.method==row.method)&(a.radius_km==row.radius_km)
        return a[mask].copy()
    def facilities(row):
        return f[(f.scope==row.scope)&(f.method==row.method)&(f.radius_km==row.radius_km)]
    # Compact grouped chart with labels legible at manuscript width.
    fig,ax=plt.subplots(figsize=(10,6.2))
    chart_rows=[(m,main_scope) for m in METHODS]+[(m,sensitivity_scope) for m in ("P-Median","MCLP") if sensitivity_scope]
    radius_colors={3:"#2171b5",5:"#238b45",10:"#e6a532"}
    offsets={3:-.23,5:0,10:.23}
    labels=[]
    max_k=1
    for j,(method,scope_name) in enumerate(chart_rows):
        discrete=method in ("P-Median","MCLP")
        label=LABELS[method]+(" (300)" if discrete and scope_name==main_scope else "")
        if scope_name!=main_scope:label+=" (828; sens.)"
        labels.append(label)
        for radius in (3,5,10):
            sub=sel[(sel.scope==scope_name)&(sel.method_base==method)&(sel.radius_km==radius)&viable]
            if sub.empty:
                if scope_name==main_scope and discrete and radius==3:
                    ax.text(1,j+offsets[radius],"inviável*",va="center",fontsize=12,color="#a11")
                continue
            row=sub.iloc[0];k=int(row.K_selected);max_k=max(max_k,k)
            ax.barh(j+offsets[radius],k,height=.2,color=radius_colors[radius],
                    hatch="///" if scope_name!=main_scope else None)
            ax.text(k+1,j+offsets[radius],str(k),va="center",fontsize=12)
    ax.set(yticks=range(len(chart_rows)),yticklabels=labels,xlabel="Instalações selecionadas")
    ax.tick_params(labelsize=13);ax.xaxis.label.set_size(14)
    ax.invert_yaxis();ax.grid(axis="x",alpha=.2);ax.set_axisbelow(True);ax.set_xlim(0,max_k*1.16+5)
    handles=[Line2D([0],[0],color=radius_colors[r],lw=8,label=f"{r} km") for r in (3,5,10)]
    fig.legend(handles=handles,title="Raio para 95% dos pedidos",fontsize=12,title_fontsize=13,loc="lower center",bbox_to_anchor=(.60,.025),ncol=3)
    fig.suptitle("Menor K encontrado por cenário de cobertura",fontsize=16)
    fig.text(.99,.005,"*300 candidatos: teto de 93,7% em 3 km. Hachura: sensibilidade separada com 828.",ha="right",fontsize=11)
    fig.tight_layout(rect=(0,.18,1,.95))
    fig.savefig(figs/"10_instalacoes_por_raio.png",dpi=170,bbox_inches="tight");plt.close(fig)
    # Tail and mean at the selected 3 km networks.
    rows=[choose(m,3,True) for m in METHODS]; rows=[r for r in rows if r is not None]
    fig,axes=plt.subplots(1,2,figsize=(10,5.8))
    x=np.arange(len(rows));names=[LABELS[r.method_base]+("\n828 (sens.)" if r.scope!=main_scope else "") for r in rows]
    for ax in axes:
        ax.set(yticks=x,yticklabels=names);ax.tick_params(labelsize=12);ax.grid(axis="x",alpha=.2)
        ax.set_axisbelow(True);ax.invert_yaxis();ax.xaxis.label.set_size(13)
    axes[0].barh(x-.2,[r.weighted_avg_distance_km for r in rows],height=.38,label="Média")
    axes[0].barh(x+.2,[r.p95_empirical_km for r in rows],height=.38,label="P95 empírico")
    axes[0].axvline(3,color="#555",ls="--",lw=1)
    axes[0].set(xlabel="Distância (km)",title="Média e P95")
    axes[1].barh(x-.2,[r.p99_empirical_km for r in rows],height=.38,label="P99 empírico",color="#fdae61")
    axes[1].barh(x+.2,[r.max_distance_km for r in rows],height=.38,label="Máximo",color="#d73027")
    axes[1].set(xlabel="Distância (km)",title="Cauda remanescente")
    fig.suptitle("Redes selecionadas para 3 km | K próprio por método\nModelos discretos com 828 candidatos: sensibilidade separada",fontsize=15)
    handles0,labels0=axes[0].get_legend_handles_labels()
    handles1,labels1=axes[1].get_legend_handles_labels()
    fig.legend(handles0+handles1,labels0+labels1,loc="lower center",ncol=4,fontsize=12,bbox_to_anchor=(.5,.02))
    fig.tight_layout(rect=(0,.14,1,.86))
    fig.savefig(figs/"11_cauda_redes_R3.png",dpi=170,bbox_inches="tight");plt.close(fig)
    scope=json.loads((args.data_dir/"geography/scope.json").read_text(encoding="utf-8-sig"))
    geo=json.loads((args.data_dir/"geography/rj_municipios_ibge.geojson").read_text(encoding="utf-8-sig"))
    # Match the official municipal subset used by the data-cleaning pipeline.
    codes=set(str(c) for c in scope.get("municipality_codes",scope.get("municipalities_ibge_codes",[])))
    if not codes:
        for v in scope.values():
            if isinstance(v,list) and len(v)==22:
                codes=set(str(c.get("ibge_code",c.get("code",""))) if isinstance(c,dict) else str(c) for c in v)
                if all(len(c)==7 for c in codes):break
                codes=set()
    rings=[]
    for feature in geo["features"]:
        if codes and str(feature["properties"]["codarea"]) not in codes:continue
        geometry=feature["geometry"]
        polys=[geometry["coordinates"]] if geometry["type"]=="Polygon" else geometry["coordinates"]
        for poly in polys:
            for ring in poly:rings.append(np.asarray(ring))
    examples=[]
    for radius in (3,5,10):
        fig,axes=plt.subplots(3,2,figsize=(10,11))
        for ax,method in zip(axes.flat,METHODS):
            row=choose(method,radius,True)
            for ring in rings:ax.plot(ring[:,0],ring[:,1],color="#a0a0a0",lw=.45,zorder=0)
            if row is None:
                ax.text(.5,.5,"Meta não atingida",transform=ax.transAxes,ha="center")
                continue
            sub=assignment(row);cent=facilities(row)
            near=sub.nearest_facility.astype(int).to_numpy()
            palette=np.array([colorsys.hsv_to_rgb((i*.61803398875)%1,.64,.76) for i in range(len(cent))])
            inside=sub.distance_km.to_numpy()<=radius
            sizes=np.sqrt(sub.n_pedidos.to_numpy())*3+3
            ax.scatter(sub.loc[inside,"lng"],sub.loc[inside,"lat"],s=sizes[inside],
                       c=palette[near[inside]],alpha=.72,lw=0)
            ax.scatter(sub.loc[~inside,"lng"],sub.loc[~inside,"lat"],s=sizes[~inside]+8,
                       facecolors="none",edgecolors="#c60000",lw=.9,zorder=4)
            ax.scatter(cent.lng,cent.lat,s=20,marker="x",color="#111",lw=.8,zorder=3)
            worst=sub.nlargest(3,"distance_km")
            for _,point in worst.iterrows():
                fc=cent[cent.facility_id==int(point.nearest_facility)].iloc[0]
                ax.plot([point.lng,fc.lng],[point.lat,fc.lat],color="#c60000",lw=.7,alpha=.8,zorder=2)
                examples.append({"scope":row.scope,"method":row.method,"radius_km":radius,
                                 "K_selected":int(row.K_selected),"CEP":point.get("CEP",point.get("customer_zip_code_prefix")),
                                 "n_pedidos":int(point.n_pedidos),"distance_km":float(point.distance_km),
                                 "facility_id":int(point.nearest_facility),"lat":point.lat,"lng":point.lng,
                                 "facility_lat":fc.lat,"facility_lng":fc.lng})
            suffix="\n828 candidatos (sens.)" if row.scope!=main_scope else ""
            ax.set(title=f"{LABELS[method]} | K={int(row.K_selected)}{suffix}\nCobertura={row.coverage_pct:.1f}% | Fora={int((sub.n_pedidos*(~inside)).sum())}",
                   xlabel="Longitude",ylabel="Latitude",xlim=(-44.15,-42.45),ylim=(-23.15,-22.15))
            ax.set_xticks([-44,-43.5,-43,-42.5])
            ax.set_aspect(1/np.cos(np.radians(-22.7)));ax.tick_params(labelsize=11);ax.title.set_size(12)
        handles=[Line2D([0],[0],marker="x",color="#111",ls="",label="PU proposto"),
                 Line2D([0],[0],marker="o",markerfacecolor="none",markeredgecolor="#c60000",ls="",label=f"Demanda além de {radius} km"),
                 Line2D([0],[0],color="#c60000",lw=.8,label="Três maiores distâncias por painel")]
        fig.legend(handles=handles,loc="lower center",ncol=3,fontsize=12)
        fig.suptitle(f"Redes selecionadas | pelo menos 95% dos pedidos em até {radius} km\nCores: atribuição ao PU mais próximo; divisas municipais IBGE",fontsize=13)
        fig.subplots_adjust(left=.09,right=.97,top=.86,bottom=.08,hspace=.72,wspace=.40)
        fig.savefig(figs/f"12_mapas_selecao_R{radius}.png",dpi=170,bbox_inches="tight");plt.close(fig)
    pd.DataFrame(examples).to_csv(out/"service_map_extremes.csv",index=False)
    # Explain the difference between native groups and operational assignment.
    fig,axes=plt.subplots(2,2,figsize=(12,10))
    native_examples=[]
    for pair,method in enumerate(("KMeans-weighted","Agglomerative-ward")):
        row=choose(method,3)
        sub=assignment(row);cent=facilities(row)
        palette=np.array([colorsys.hsv_to_rgb((i*.61803398875)%1,.64,.76) for i in range(len(cent))])
        for ax,label_col,title in zip(axes[pair],("native_label","nearest_facility"),("Grupos de formação","PU mais próximo")):
            for ring in rings:ax.plot(ring[:,0],ring[:,1],color="#a0a0a0",lw=.45,zorder=0)
            labels=sub[label_col].astype(int).to_numpy()
            ax.scatter(sub.lng,sub.lat,s=np.sqrt(sub.n_pedidos)*3+3,c=palette[labels],alpha=.72,lw=0)
            ax.scatter(cent.lng,cent.lat,s=20,marker="x",c="#111",lw=.8)
            changed=sub[sub.native_label!=sub.nearest_facility].copy()
            changed["reduction_km"]=changed.native_distance_km-changed.distance_km
            chosen=changed.nlargest(3,"reduction_km")
            for _,point in chosen.iterrows():
                fid=int(point[label_col]);fc=cent[cent.facility_id==fid].iloc[0]
                ax.plot([point.lng,fc.lng],[point.lat,fc.lat],c="#c60000",lw=1)
                ax.scatter([point.lng],[point.lat],s=65,facecolors="none",edgecolors="#c60000",lw=1)
                if label_col=="native_label":
                    native_examples.append({"method":method,"K_selected":int(row.K_selected),"CEP":point.CEP,
                        "n_pedidos":int(point.n_pedidos),"native_distance_km":point.native_distance_km,
                        "nearest_distance_km":point.distance_km,"reduction_km":point.reduction_km})
            ax.set(title=f"{LABELS[method]} | K={int(row.K_selected)} | {title}",
                   xlabel="Longitude",ylabel="Latitude",xlim=(-44.15,-42.45),ylim=(-23.15,-22.15))
            ax.set_xticks([-44,-43.5,-43,-42.5])
            ax.set_aspect(1/np.cos(np.radians(-22.7)));ax.tick_params(labelsize=9)
    fig.suptitle("O P95 seleciona o tamanho da rede; os grupos nativos permanecem distintos\nLinhas vermelhas: três maiores reduções ao atribuir ao PU mais próximo",fontsize=13)
    save(fig,figs/"13_grupos_nativos_vs_proximidade_R3.png")
    pd.DataFrame(native_examples).to_csv(out/"service_native_examples.csv",index=False)

    # Municipal diagnostics use each order's municipality, not the modal prefix label.
    orders=pd.read_csv(args.data_dir/"pedidos_rmrj_geo.csv",dtype={"customer_zip_code_prefix":str})
    if orders.order_id.duplicated().any() or len(orders)!=9691:
        raise ValueError("Order-level municipal input is not the audited study cohort")
    municipal=[]
    for _,row in sel[viable].iterrows():
        sub=assignment(row)
        key="CEP" if "CEP" in sub else "customer_zip_code_prefix"
        assigned=orders.merge(sub[[key,"distance_km"]],left_on="customer_zip_code_prefix",right_on=key,
                              how="left",validate="many_to_one")
        if assigned.distance_km.isna().any() or len(assigned)!=len(orders):
            raise ValueError("Municipal join lost or multiplied demand")
        for city,g in assigned.groupby("city_norm"):
            covered=int((g.distance_km<=row.radius_km).sum())
            municipal.append({"scope":row.scope,"method":row.method,"radius_km":row.radius_km,
                              "K_selected":int(row.K_selected),"city_norm":city,"orders":len(g),
                              "orders_covered":covered,"orders_outside":len(g)-covered,
                              "coverage_pct":100*covered/len(g),"p95_empirical_km":quantile(g.distance_km,.95),
                              "max_distance_km":float(g.distance_km.max())})
    pd.DataFrame(municipal).to_csv(out/"service_by_municipality.csv",index=False)
    print(f"Generated six scientific figures and municipal diagnostics in {figs}",flush=True)
if __name__=="__main__":main()
