"""Independent v22 artifact verification; does not import repository modules.

Recomputes service from exported facilities, immutable demand and per-order cities.
An independently assembled MILP repeats one finite partial-cover benchmark, using
the installed SciPy/HiGHS solver (not an independent second solver).
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import platform
import shutil
import time
import unicodedata
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[1]
EARTH_KM = 6371.0088
TOL_KM = 1e-7
TOL_DEG = 1e-10
TOL_PCT = 1e-7


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).strip().lower())
                   if not unicodedata.combining(c))


def prefixes(values):
    return pd.Series(values, dtype="string").str.replace(r"\.0$", "", regex=True).str.zfill(5)


def resolve_input_location(metadata, filename):
    """Resolve physical input independently of canonical scientific hash keys."""
    hashes=metadata["input_hashes"]
    keys=[key for key in hashes if Path(key).name==filename]
    if len(keys)!=1:raise ValueError("Expected one hashed input named "+filename)
    key=keys[0]
    locations=metadata.get("input_locations",{}) or metadata.get("input_paths",{})
    source=Path(locations.get(key,key))
    if not source.is_absolute() and key not in locations:
        raise ValueError("Canonical input key has no recorded physical location: "+key)
    return source,hashes[key]


def select_output_manifest(metadata, directory):
    """Choose the declared final manifest before checking any file hashes.

    Consolidated F2 keeps its historical output_hashes and final raw_output_hashes;
    their provenance must match the preserved initial metadata. Native cold runs
    have their own final output_hashes and need no consolidation exception.
    """
    if "raw_output_hashes" not in metadata:
        return metadata.get("output_hashes",{}),None
    directory=Path(directory)
    candidates=[directory/"metadata_initial_execution.json",
                directory/"provenance/metadata_initial_execution.json"]
    existing=[p for p in candidates if p.is_file()]
    if not existing:raise ValueError("Consolidated manifest lacks preserved initial metadata")
    initial=json.loads(existing[0].read_text(encoding="utf-8-sig"))
    if not metadata.get("initial_execution_signature") or initial.get("signature_sha256")!=metadata["initial_execution_signature"]:
        raise ValueError("Consolidated manifest initial signature differs from provenance")
    if initial.get("output_hashes")!=metadata.get("output_hashes"):
        raise ValueError("Historical output_hashes differ from preserved initial manifest")
    return metadata["raw_output_hashes"],existing[0]


def validated_weights(weights):
    values = np.asarray(weights)
    if values.ndim != 1 or not len(values) or not np.isfinite(values.astype(float)).all():
        raise ValueError("Demand must contain finite positive integer counts")
    integers = values.astype(np.int64)
    if np.any(integers <= 0) or not np.array_equal(integers, values):
        raise ValueError("Demand must contain positive integer counts")
    if sum(map(int, integers)) > 2**53:
        raise ValueError("Demand exceeds exact integer-to-float arithmetic")
    return integers


def distance_matrix(coords, centers, metric="haversine"):
    a, b = np.asarray(coords, float), np.asarray(centers, float)
    if a.ndim != 2 or b.ndim != 2 or a.shape[1] != 2 or b.shape[1] != 2 or not len(b):
        raise ValueError("Nonempty [latitude,longitude] coordinate matrices required")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Nonfinite coordinates")
    if np.any(np.abs(a[:, 0]) > 90) or np.any(np.abs(b[:, 0]) > 90):
        raise ValueError("Invalid latitude")
    if np.any(np.abs(a[:, 1]) > 180) or np.any(np.abs(b[:, 1]) > 180):
        raise ValueError("Invalid longitude")
    answer = np.empty((len(a), len(b)), dtype=float)
    geod = Geod(ellps="WGS84") if metric == "geodesic" else None
    if metric not in ("haversine", "geodesic"):
        raise ValueError("Undeclared distance metric")
    for first in range(0, len(a), 128):
        section = a[first:first+128]
        if geod:
            la, lb = np.broadcast_arrays(section[:, 0, None], b[None, :, 0])
            lo, lob = np.broadcast_arrays(section[:, 1, None], b[None, :, 1])
            answer[first:first+128] = geod.inv(lo.ravel(), la.ravel(), lob.ravel(), lb.ravel())[2].reshape(la.shape)/1000
        else:
            la, lb = np.deg2rad(section[:, 0, None]), np.deg2rad(b[None, :, 0])
            dl = np.deg2rad(b[None, :, 1]-section[:, 1, None])
            h = np.sin((lb-la)/2)**2 + np.cos(la)*np.cos(lb)*np.sin(dl/2)**2
            h = np.clip(h, 0, 1)
            # atan2 form differs from production arcsin implementation.
            answer[first:first+128] = 2*EARTH_KM*np.arctan2(np.sqrt(h), np.sqrt(1-h))
    return answer


def quantile(d, weights, q):
    q = Fraction(q)
    if not 0 < q <= 1:
        raise ValueError("Quantile must be in (0,1]")
    w = validated_weights(weights)
    d = np.asarray(d, float)
    if d.shape != w.shape or not np.isfinite(d).all() or np.any(d < 0):
        raise ValueError("Finite nonnegative distances matching demand required")
    rank = (int(w.sum())*q.numerator+q.denominator-1)//q.denominator
    order = np.argsort(d, kind="stable")
    return float(d[order[np.searchsorted(np.cumsum(w[order]), rank)]])


def recalculate_metrics(d, weights, radius):
    d = np.asarray(d, float)
    w = validated_weights(weights)
    total = int(w.sum())
    covered = int(w[d <= radius].sum())
    required = (95*total+99)//100
    repeated = np.repeat(d, w)
    return dict(total_orders=total, required_orders=required, covered_orders=covered,
                outside_orders=total-covered, coverage_pct=100*covered/total,
                target_met=covered >= required,
                weighted_avg_distance_km=float(np.dot(d, w)/total),
                median_empirical_km=quantile(d, w, Fraction(1, 2)),
                p95_empirical_km=quantile(d, w, Fraction(95, 100)),
                p99_empirical_km=quantile(d, w, Fraction(99, 100)),
                p95_linear_km=float(np.quantile(repeated, .95, method="linear")),
                p99_linear_km=float(np.quantile(repeated, .99, method="linear")),
                max_distance_km=float(d.max()))


def fractional_redistribution(records,demand,centers,radius,metric="haversine"):
    records=records[records.CEP.isin(demand.CEP)].copy()
    counts=records.groupby("CEP").size()
    if not set(demand.CEP).issubset(counts.index):raise ValueError("Missing retained records for demand prefix")
    weights=records.CEP.map(dict(zip(demand.CEP,demand.n_pedidos))).to_numpy(float)/records.CEP.map(counts).to_numpy(float)
    total=float(weights.sum())
    if not math.isclose(total,int(demand.n_pedidos.sum()),rel_tol=0,abs_tol=1e-8):
        raise ValueError("Fractional redistribution did not conserve orders")
    coords=records[["geolocation_lat","geolocation_lng"]].to_numpy(float)
    distances=np.empty(len(coords))
    for start in range(0,len(coords),512):distances[start:start+512]=distance_matrix(coords[start:start+512],centers,metric).min(axis=1)
    order=np.argsort(distances,kind="stable");cumulative=np.cumsum(weights[order])
    def empirical(q):return float(distances[order[min(np.searchsorted(cumulative,q*total),len(order)-1)]])
    covered=float(weights[distances<=radius].sum())
    return dict(redistributed_N_fractional=total,redistributed_covered_fractional=covered,
                redistributed_coverage_pct=100*covered/total,redistributed_mean_km=float(np.dot(distances,weights)/total),
                redistributed_p95_km=empirical(.95),redistributed_p99_km=empirical(.99),redistributed_max_km=float(distances.max()))


def municipal_profile(orders, demand, d, radius, city_column="city_norm", names=()):
    if orders.order_id.duplicated().any():
        raise ValueError("Duplicated order_id")
    counts = orders.groupby("CEP").size()
    expected = pd.Series(demand.n_pedidos.to_numpy(), index=demand.CEP)
    if set(counts.index) != set(expected.index) or not np.array_equal(counts.reindex(expected.index).to_numpy(), expected.to_numpy()):
        raise ValueError("Order counts do not reproduce postal demand")
    if orders[city_column].isna().any():
        raise ValueError("Missing per-order municipality")
    lookup = dict(zip(demand.CEP, d))
    frame = orders[["order_id", "CEP", city_column]].copy()
    frame["d"] = frame.CEP.map(lookup)
    frame["covered"] = frame.d <= radius
    profile = frame.groupby(city_column).agg(total_orders=("order_id", "size"),
        covered_orders=("covered", "sum"), mean_distance_km=("d", "mean"),
        max_distance_km=("d", "max"))
    profile = profile.reindex(sorted(set(profile.index)|set(names)), fill_value=0)
    profile["outside_orders"] = profile.total_orders-profile.covered_orders
    profile["coverage_pct"] = np.where(profile.total_orders > 0, 100*profile.covered_orders/profile.total_orders, np.nan)
    profile.index.name = "city"
    return profile.reset_index()


def independent_cover_benchmark(coords, weights, candidates, radius=5., time_limit=300.):
    """Own sparse binary partial-cover model; finite candidates only."""
    w = validated_weights(weights)
    D = distance_matrix(coords, np.asarray(coords)[candidates])
    inside = D <= radius
    n, m = inside.shape
    ceiling = int(w[inside.any(axis=1)].sum())
    required = (95*int(w.sum())+99)//100
    if ceiling < required:
        return dict(status=2, candidate_ceiling_orders=ceiling, required_orders=required,
                    solver="independent structural bound", certified_infeasible=True)
    demand_row, facility_col = np.nonzero(inside)
    rr = np.concatenate([demand_row, np.arange(n), np.full(n, n)])
    cc = np.concatenate([facility_col, m+np.arange(n), m+np.arange(n)])
    vv = np.concatenate([-np.ones(len(demand_row)), np.ones(n), w.astype(float)])
    A = coo_matrix((vv, (rr, cc)), shape=(n+1, m+n)).tocsc()
    lower = np.full(n+1, -np.inf); lower[n] = required
    upper = np.zeros(n+1); upper[n] = np.inf
    c = np.r_[np.ones(m), np.zeros(n)]
    started = time.perf_counter()
    result = milp(c, integrality=np.r_[np.ones(m), np.zeros(n)],
                  bounds=Bounds(np.zeros(m+n), np.ones(m+n)),
                  constraints=LinearConstraint(A, lower, upper),
                  options={"time_limit": float(time_limit), "mip_rel_gap": 0.})
    report = dict(solver="SciPy milp/HiGHS", independent_second_solver=False,
                  status=int(result.status), message=str(result.message),
                  runtime_s=time.perf_counter()-started, primal_objective=None,
                  dual_bound=None, gap=None, K=None, covered_orders=None,
                  required_orders=required, candidate_ceiling_orders=ceiling)
    for field, attr in (("primal_objective", "fun"), ("dual_bound", "mip_dual_bound"), ("gap", "mip_gap")):
        value = getattr(result, attr, None)
        report[field] = None if value is None else float(value)
    if result.x is not None:
        selected = np.flatnonzero(result.x[:m] > .5)
        covered = int(w[inside[:, selected].any(axis=1)].sum())
        report.update(K=int(len(selected)), covered_orders=covered,
                      selected_postal_positions=np.asarray(candidates)[selected].tolist(),
                      primal_verified=covered >= required and abs(result.x[:m]-np.round(result.x[:m])).max() <= 1e-6)
    return report


ALIASES = {
 "total_orders": ("total_orders", "N_orders"), "required_orders": ("required_orders",),
 "covered_orders": ("covered_orders",), "outside_orders": ("outside_orders", "uncovered_orders"),
 "coverage_pct": ("coverage_pct",), "target_met": ("target_met", "feasible"),
 "weighted_avg_distance_km": ("weighted_avg_distance_km", "weighted_mean_km"),
 "median_empirical_km": ("median_empirical_km",),
 "p95_empirical_km": ("p95_empirical_km", "p95_km"),
 "p99_empirical_km": ("p99_empirical_km", "p99_km"),
 "p95_linear_km": ("p95_linear_km",), "p99_linear_km": ("p99_linear_km",),
 "max_distance_km": ("max_distance_km", "max_km")
}


def boolean(value):
    if isinstance(value, str):
        if value.lower() not in ("true", "false"):
            raise ValueError("Invalid Boolean value")
        return value.lower() == "true"
    return bool(value)


def postal_candidate_positions(frame, regime, union, main_prefixes=()):
    legacy=regime.endswith("_legacy_order")
    if legacy:regime=regime.removesuffix("_legacy_order")
    if regime.endswith("_main300fixed"):
        lookup=dict(zip(frame.CEP,range(len(frame))))
        return np.asarray([lookup[p] for p in main_prefixes],dtype=int)
    eligible=np.arange(len(frame))
    if regime in ("J825","J_union825"):
        xy=frame[["lat","lng"]].to_numpy(float)
        eligible=eligible[np.asarray(shapely.intersects_xy(union,xy[:,1],xy[:,0]),bool)]
    if legacy:return np.asarray(sorted(eligible,key=lambda i:frame.CEP.iloc[i]),dtype=int)
    reverse=regime in ("J300_reverse","J300_tie_reverse")
    ordered=sorted(eligible,key=lambda i:(-int(frame.n_pedidos.iloc[i]),
                    int(frame.CEP.iloc[i])*(-1 if reverse else 1)))
    if regime in ("J828","J825","J_all828","J_union825"):
        return np.asarray(ordered,dtype=int)
    return np.asarray(ordered[:300],dtype=int)


class Auditor:
    def __init__(self, args):
        self.args = args
        self.failures, self.warnings, self.networks, self.evidence, self.files = [], [], [], [], {}
        self.pending, self.benchmark = [], None
        self.cache = {}
        self.check_count = 0

    def check(self, condition, name, expected=None, observed=None):
        self.check_count += 1
        if not condition:
            self.failures.append(dict(check=name, expected=clean(expected), observed=clean(observed)))

    def read_csv(self, path):
        path = Path(path)
        self.files[str(path.resolve())] = sha(path)
        df = pd.read_csv(path, dtype={"CEP":str, "postal_prefix":str, "customer_zip_code_prefix":str,
                                     "geolocation_zip_code_prefix":str})
        for col in ("CEP", "postal_prefix", "customer_zip_code_prefix"):
            if col in df:
                df[col] = prefixes(df[col]).to_numpy()
        return df

    def read_json(self, path):
        path = Path(path)
        self.files[str(path.resolve())] = sha(path)
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def demand_frame(self, path):
        df = self.read_csv(path)
        prefix = "CEP" if "CEP" in df else "customer_zip_code_prefix"
        df = df.rename(columns={prefix:"CEP"})
        self.check(not df.CEP.duplicated().any(), str(path)+": unique postal prefix")
        validated_weights(df.n_pedidos.to_numpy())
        return df.reset_index(drop=True)

    def compare(self, observed, expected, name, tol=TOL_KM):
        if isinstance(expected, (bool, np.bool_)):
            ok = boolean(observed) == bool(expected)
        elif expected is None:
            ok = observed is None or pd.isna(observed)
        elif tol==0:
            ok = float(observed)==float(expected)
        else:
            ok = math.isfinite(float(observed)) and math.isclose(float(observed), float(expected), rel_tol=1e-9, abs_tol=tol)
        self.check(ok, name, expected, observed)

    def compare_metrics(self, row, metrics, key):
        for field, aliases in ALIASES.items():
            for alias in aliases:
                if alias in row and pd.notna(row[alias]):
                    tol = TOL_PCT if field == "coverage_pct" else (0 if field in ("total_orders","required_orders","covered_orders","outside_orders") else TOL_KM)
                    self.compare(row[alias], metrics[field], key+":"+alias, tol)

    def load(self):
        a = self.args
        self.demand = self.demand_frame(a.data_dir/"demanda_por_cep.csv")
        self.orders = self.read_csv(a.data_dir/"pedidos_rmrj_geo.csv").rename(columns={"customer_zip_code_prefix":"CEP"})
        scope = self.read_json(a.data_dir/"geography/scope.json")
        features = self.read_json(a.data_dir/"geography/rj_municipios_ibge.geojson")
        codes = set(map(str,scope["municipality_codes"]))
        geometries = [shape(f["geometry"]) for f in features["features"] if str(f["properties"]["codarea"]) in codes]
        self.check(len(geometries)==len(codes), "Complete scoped municipal geometry",len(codes),len(geometries))
        self.union = unary_union(geometries)
        self.names = sorted(normalize(scope["municipalities"][code]) for code in codes)
        municipal_profile(self.orders,self.demand,np.zeros(len(self.demand)),0,"city_norm")
        self.check(int(self.demand.n_pedidos.sum())==9691 and len(self.demand)==828,
                   "Principal denominator frozen", [828,9691],[len(self.demand),int(self.demand.n_pedidos.sum())])

    def inside(self, coords):
        coords = np.asarray(coords,float)
        return np.asarray(shapely.intersects_xy(self.union,coords[:,1],coords[:,0]),bool)

    def network(self, key, row, demand, orders, facilities, assignments, metric="haversine", municipal=None, city_column="city_norm"):
        facilities = facilities.sort_values("facility_id").reset_index(drop=True)
        ids = facilities.facility_id.to_numpy(int)
        self.check(np.array_equal(ids,np.arange(len(ids))), key+": consecutive facility IDs")
        centers = facilities[["lat","lng"]].to_numpy(float)
        K = len(centers)
        selected = row.get("K_selected",row.get("K",row.get("n_facilities")))
        self.compare(selected,K,key+": K",0)
        for field,value in (("n_facilities",K),("unique_facility_coordinates",len(np.unique(centers,axis=0)))):
            if field in row and pd.notna(row[field]):self.compare(row[field],value,key+":"+field,0)
        positions=row.get("_candidate_positions")
        if positions is not None:
            allowed=demand[["lat","lng"]].iloc[positions].to_numpy(float)
            membership=np.any(np.max(np.abs(centers[:,None,:]-allowed[None,:,:]),axis=2)<=TOL_DEG,axis=1)
            self.check(membership.all(),key+": facilities belong to declared postal candidate set")
        if "source_kind" in facilities:
            for exported in facilities[facilities.source_kind.str.startswith("postal")].to_dict("records"):
                source_position=int(exported["source_position"])
                self.check(0<=source_position<len(demand),key+": valid postal source position")
                for col in ("lat","lng"):
                    self.compare(exported[col],demand[col].iloc[source_position],key+": postal candidate "+str(source_position)+":"+col,TOL_DEG)
        radius = float(row["radius_km"])
        D = distance_matrix(demand[["lat","lng"]].to_numpy(float),centers,metric)
        nearest = D.argmin(axis=1)
        d = D[np.arange(len(demand)),nearest]
        metrics = recalculate_metrics(d,demand.n_pedidos.to_numpy(),radius)
        self.compare_metrics(row,metrics,key)
        prefix = "CEP" if "CEP" in assignments else "postal_prefix"
        assignments = assignments.rename(columns={prefix:"CEP"})
        self.check(len(assignments)==len(demand) and not assignments.CEP.duplicated().any(),key+": complete unique assignments")
        self.check(set(assignments.CEP)==set(demand.CEP),key+": unchanged demand membership")
        assigned = assignments.set_index("CEP").reindex(demand.CEP)
        self.check(np.array_equal(assigned.n_pedidos.to_numpy(),demand.n_pedidos.to_numpy()),key+": assignment weights")
        for col in ("lat","lng"):
            if col in assigned:
                self.check(np.allclose(assigned[col],demand[col],rtol=0,atol=TOL_DEG),key+": demand "+col)
        reported = assigned.nearest_facility.to_numpy(int)
        self.check(np.all((reported >=0)&(reported<K)),key+": valid facility references")
        reported_d = D[np.arange(len(demand)),reported]
        self.check(np.allclose(reported_d,d,rtol=1e-9,atol=TOL_KM),key+": nearest facility",0,float(np.max(reported_d-d)))
        self.check(np.allclose(assigned.distance_km,d,rtol=1e-9,atol=TOL_KM),key+": exported nearest distances",
                   0,float(np.max(np.abs(assigned.distance_km.to_numpy()-d))))
        for field,expected in (("outside_R",d>radius),("inside_R",d<=radius)):
            if field in assigned:
                flags = np.array([boolean(x) for x in assigned[field]])
                self.check(np.array_equal(flags,expected),key+":"+field)
        if "native_label" in assigned:
            native_labels = assigned.native_label.to_numpy(int)
            valid = (native_labels>=0)&(native_labels<K)
            self.check(valid.all(),key+": valid native labels")
            native = D[np.arange(len(demand)),native_labels]
            if "native_distance_km" in assigned:
                self.check(np.allclose(assigned.native_distance_km,native,rtol=1e-9,atol=TOL_KM),key+": native distances")
            if "native_max_km" in row and pd.notna(row["native_max_km"]):
                self.compare(row["native_max_km"],native.max(),key+": native maximum")
            for field,value in (("reassigned_prefixes",int((native_labels!=reported).sum())),
                                ("reassigned_orders",int(demand.n_pedidos.to_numpy()[native_labels!=reported].sum()))):
                if field in row and pd.notna(row[field]):self.compare(row[field],value,key+":"+field,0)
            if "n_native_clusters" in row and pd.notna(row["n_native_clusters"]):
                self.compare(row["n_native_clusters"],len(np.unique(native_labels)),key+": native cluster count",0)
        loads = np.bincount(reported,weights=demand.n_pedidos,minlength=K).astype(np.int64)
        self.check(int(loads.sum())==metrics["total_orders"],key+": load conservation")
        if "nearest_assigned_orders" in facilities:
            self.check(np.array_equal(facilities.nearest_assigned_orders.to_numpy(),loads),key+": exported loads")
        inside = self.inside(centers)
        for flag,value in (("inside_union",inside),("inside_municipal_union",inside),("outside_municipal_union",~inside)):
            if flag in facilities:
                self.check(np.array_equal(np.array([boolean(x) for x in facilities[flag]]),value),key+":"+flag)
        for field in ("selected_outside_union","outside_union_facilities"):
            if field in row and pd.notna(row[field]):self.compare(row[field],int((~inside).sum()),key+":"+field,0)
        if "orders_nearest_to_outside_facilities" in row and pd.notna(row["orders_nearest_to_outside_facilities"]):
            self.compare(row["orders_nearest_to_outside_facilities"],int(demand.n_pedidos.to_numpy()[~inside[reported]].sum()),key+": orders nearest to external facilities",0)
        profile = municipal_profile(orders,demand,d,radius,city_column,names=self.names)
        self.check(int(profile.total_orders.sum())==metrics["total_orders"],key+": municipal denominator")
        self.check(int(profile.covered_orders.sum())==metrics["covered_orders"],key+": municipal coverage")
        if municipal is not None:
            city = next(c for c in ("city_norm","municipality","city") if c in municipal)
            exp = municipal.set_index(city)
            for rec in profile.to_dict("records"):
                name = rec["city"]
                if rec["total_orders"] or name in exp.index:
                    self.check(name in exp.index,key+": municipality "+name)
                    if name not in exp.index:continue
                    exported = exp.loc[name]
                    for field,aliases in {"total_orders":("total_orders","N_orders","orders"),
                       "covered_orders":("covered_orders","orders_covered"),"outside_orders":("outside_orders","uncovered_orders","orders_outside"),
                       "coverage_pct":("coverage_pct",),"mean_distance_km":("mean_distance_km",),"max_distance_km":("max_distance_km",)}.items():
                        for alias in aliases:
                            if alias in exported and pd.notna(exported[alias]):
                                self.compare(exported[alias],rec[field],key+":"+name+":"+alias,
                                             0 if field.endswith("orders") else TOL_KM)
        zero = (profile.total_orders>0)&(profile.covered_orders==0)
        low = (profile.total_orders>0)&(profile.coverage_pct<80)
        rio = int(profile.loc[profile.city.eq("rio de janeiro"),"outside_orders"].sum())
        summaries = {"municipalities_zero":int(zero.sum()),"municipalities_below80":int(low.sum()),
                     "orders_in_zero_municipalities":int(profile.loc[zero,"total_orders"].sum()),
                     "orders_in_below80_municipalities":int(profile.loc[low,"total_orders"].sum()),
                     "Rio_outside_orders":rio,"Rio_share_of_outside_pct":100*rio/metrics["outside_orders"] if metrics["outside_orders"] else None}
        for field, aliases in {"municipalities_zero":("municipalities_zero","zero_coverage_municipalities"),
          "municipalities_below80":("municipalities_below80","below_80pct_municipalities"),
          "orders_in_zero_municipalities":("orders_in_zero_municipalities",),
          "orders_in_below80_municipalities":("orders_in_below80_municipalities",),
          "Rio_outside_orders":("Rio_outside_orders","rio_uncovered_orders","rio_outside_orders"),
          "Rio_share_of_outside_pct":("Rio_share_of_outside_pct","rio_share_of_uncovered_pct","rio_share_outside_pct")}.items():
            for alias in aliases:
                if alias in row and pd.notna(row[alias]):
                    self.compare(row[alias],summaries[field] if summaries[field] is not None else 0,key+":"+alias,TOL_PCT)
        self.networks.append(dict(key=key,metric=metric,K=K,**metrics,**summaries,
                                  outside_municipal_union_facilities=int((~inside).sum()),
                                  accepted_numerical_ties=int((reported!=nearest).sum())))
        self.cache[key] = dict(demand=demand,facilities=facilities,distances=d,reported_nearest=reported,
                               native=None if "native_label" not in assigned else native,
                               native_labels=None if "native_label" not in assigned else native_labels)
        return metrics

    @staticmethod
    def subsets(df, fields):
        return {tuple(key if isinstance(key,tuple) else (key,)):value
                for key,value in df.groupby(fields,dropna=False,sort=False)}

    def validate_main(self):
        p = self.args.main_dir
        meta = self.read_json(p/"service_metadata.json")
        self.check(meta.get("run_state")=="complete","Main complete")
        self.check(meta["protocol"]["data_sha256"]==sha(self.args.data_dir/"demanda_por_cep.csv"),"Main declared demand hash")
        selection = self.read_csv(p/"service_selection.csv")
        fac = self.subsets(self.read_csv(p/"service_facilities.csv"),["scope","method","radius_km"])
        ass = self.subsets(self.read_csv(p/"service_assignments.csv"),["scope","method","radius_km"])
        muni_path = p/"service_by_municipality_v22.csv"
        muni = self.subsets(self.read_csv(muni_path),["scope","method","radius_km"]) if muni_path.exists() else {}
        if not muni:self.pending.append("Main municipality figure CSV absent")
        geo_path = p/"facility_geography_v22.csv"
        geo = self.subsets(self.read_csv(geo_path),["scope","method","radius_km"]) if geo_path.exists() else {}
        curves = self.read_csv(p/"service_curves.csv")
        for row in selection.to_dict("records"):
            tag = (row["scope"],row["method"],float(row["radius_km"]))
            key = "main:"+":".join(map(str,tag))
            if row["status"]=="selected":
                if tag[1] in ("P-Median","MCLP"):
                    row["_candidate_positions"]=postal_candidate_positions(self.demand,"J828" if tag[0]=="all_candidates_sensitivity" else "J300",self.union)
                metrics=self.network(key,row,self.demand,self.orders,geo.get(tag,fac[tag]),ass[tag],municipal=muni.get(tag))
                self.check(metrics["target_met"],key+": selected feasible")
                group=curves[(curves.scope==tag[0])&(curves.method==tag[1])&(curves.radius_km==tag[2])]
                kcol="K_target" if "K_target" in group else "K"
                K=int(row["K_selected"]); seeds=[42,0,1,2,3] if tag[1]=="KMeans-weighted" else [-1]
                self.check(set(group.loc[group[kcol]<=K,kcol].astype(int))==set(range(1,K+1)),key+": all smaller integers logged")
                first=None
                for k in range(1,K+1):
                    g=group[group[kcol]==k]
                    observed=dict(zip(g.seed.astype(int),g.covered_orders.astype(int)))
                    if set(seeds).issubset(observed) and all(observed[s]>=metrics["required_orders"] for s in seeds):
                        first=k;break
                self.compare(first,K,key+": first feasible logged K",0)
            elif row["status"]=="structurally_infeasible":
                pos=np.array(sorted(range(len(self.demand)),key=lambda i:(-int(self.demand.n_pedidos.iloc[i]),self.demand.CEP.iloc[i]))[:300])
                D=distance_matrix(self.demand[["lat","lng"]],self.demand[["lat","lng"]].iloc[pos])
                ceiling=int(self.demand.n_pedidos.to_numpy()[(D<=tag[2]).any(axis=1)].sum())
                self.compare(row["candidate_ceiling_orders"],ceiling,key+": independent structural ceiling",0)
                self.check(ceiling<(95*int(self.demand.n_pedidos.sum())+99)//100,key+": independent infeasibility")
            else:self.check(False,key+": unexpected status","selected/structurally_infeasible",row["status"])
        self.evidence.append(dict(section="main",rows=len(selection),networks=len(fac),
                                 minimum_K_check="against exported curve grid; no independent refit of every K"))

    def validate_exact(self):
        p=self.args.exact_dir
        meta=self.read_json(p/"exact_metadata.json")
        self.check(meta.get("run_state")=="complete","Exact complete")
        for name,expected in meta.get("output_sha256",{}).items():self.check(sha(p/name)==expected,"Exact declared hash:"+name)
        results=self.read_json(p/"exact_results.json")
        fac=self.subsets(self.read_csv(p/"exact_facilities.csv"),["job_id"])
        ass=self.subsets(self.read_csv(p/"exact_assignments.csv"),["job_id"])
        muni=self.subsets(self.read_csv(p/"exact_municipalities.csv"),["job_id"])
        for row in results:
            key="exact:"+row["job_id"]
            if row["has_primal_solution"]:
                tag=(row["job_id"],)
                if row["candidate_set"] in ("J300","J300_reverse","J828","J825"):
                    row["_candidate_positions"]=postal_candidate_positions(self.demand,row["candidate_set"],self.union)
                metrics=self.network(key,row,self.demand,self.orders,fac[tag],ass[tag],municipal=muni[tag])
                objective=(row["K"] if row["problem"]=="partial_cover" else
                           -metrics["covered_orders"] if row["problem"]=="maximal_cover" else
                           metrics["weighted_avg_distance_km"]*metrics["total_orders"])
                self.compare(row["primal_objective"],objective,key+": independently computed primal objective",1e-6)
                self.compare(row["dual_bound"],row["primal_objective"],key+": closed primal-dual certificate",1e-6)
                self.check(row.get("primal_verified") is True,key+": declared primal validity")
                self.check(row.get("solver_certified_optimal") is True and row["status"]==0 and abs(row["mip_gap"])<=1e-8,key+": internally consistent optimum certificate")
                if row.get("mandatory_radius_km") is not None:
                    self.check(self.cache[key]["distances"].max()<=float(row["mandatory_radius_km"]),key+": mandatory proximity")
            else:
                reverse=row["candidate_set"]=="J300_reverse"
                order=sorted(range(len(self.demand)),key=lambda i:(-int(self.demand.n_pedidos.iloc[i]),int(self.demand.CEP.iloc[i])*(-1 if reverse else 1)))
                D=distance_matrix(self.demand[["lat","lng"]],self.demand[["lat","lng"]].iloc[order[:300]])
                ceiling=int(self.demand.n_pedidos.to_numpy()[(D<=float(row["radius_km"])).any(axis=1)].sum())
                self.compare(row["candidate_ceiling_orders"],ceiling,key+": independent coverage ceiling",0)
                self.check(ceiling<row["required_orders"] and row["certified_infeasible"],key+": structural infeasibility")
        self.evidence.append(dict(section="exact",rows=len(results),
                                 optimality_scope="one independent model rerun; remaining solver certificates checked for consistency and all primals recomputed"))

    def sensitivity_coordinates(self, main, estimator, metadata):
        if estimator not in ("median","dedup_full"):return main
        if estimator in self.cache:return self.cache[estimator]
        raw=self.retained_raw_records(metadata)
        raw=raw[raw.CEP.isin(main.CEP)].copy()
        if estimator=="dedup_full":
            raw=raw.drop_duplicates(["geolocation_zip_code_prefix","geolocation_lat","geolocation_lng","geolocation_city","geolocation_state"])
        grouped=raw.groupby("CEP")[["geolocation_lat","geolocation_lng"]]
        frame=grouped.median() if estimator=="median" else grouped.mean()
        result=main.copy();result[["lat","lng"]]=frame.reindex(main.CEP).to_numpy()
        self.cache[estimator]=result
        return result

    def retained_raw_records(self,metadata):
        if "raw_retained" in self.cache:return self.cache["raw_retained"]
        source,expected_hash=resolve_input_location(metadata,"olist_geolocation_dataset.csv")
        self.check(sha(source)==expected_hash,"Raw geolocation declared hash")
        raw=self.read_csv(source)
        raw["source_row_number"]=np.arange(len(raw))+2
        raw["CEP"]=prefixes(raw.geolocation_zip_code_prefix).to_numpy()
        coords=raw[["geolocation_lat","geolocation_lng"]].to_numpy(float)
        valid=np.isfinite(coords).all(axis=1)&(np.abs(coords[:,0])<=90)&(np.abs(coords[:,1])<=180)
        inside=np.zeros(len(raw),bool);inside[valid]=self.inside(coords[valid])
        decisions=self.read_csv(self.args.data_dir/"geography/geolocation_review_decisions.csv")
        retained=decisions.loc[decisions.decision.eq("retain_boundary_uncertainty"),"source_row_number"].to_numpy()
        exceptional=raw.source_row_number.isin(retained).to_numpy()&raw.CEP.isin(self.demand.CEP).to_numpy()
        raw=raw[valid&(inside|exceptional)].copy()
        means=raw[raw.CEP.isin(self.demand.CEP)].groupby("CEP")[["geolocation_lat","geolocation_lng"]].mean().reindex(self.demand.CEP).to_numpy()
        self.check(np.allclose(means,self.demand[["lat","lng"]],rtol=0,atol=TOL_DEG),"Independent retained-record means reproduce principal demand")
        self.cache["raw_retained"]=raw
        return raw

    def validate_sensitivity(self):
        p=self.args.sensitivity_dir
        if not (p/"metadata.json").exists():
            self.pending.append("Sensitivity artifacts absent");return
        meta=self.read_json(p/"metadata.json")
        if not meta.get("complete",False):
            self.pending.append("Sensitivity execution incomplete; its active CSVs were not read");return
        final_hashes,provenance=select_output_manifest(meta,p)
        if provenance is not None:
            self.files[str(provenance.resolve())]=sha(provenance)
            self.evidence.append(dict(section="sensitivity_manifest",selected="raw_output_hashes",
                reason="Consolidated F2; initial signature and historical manifest match preserved provenance",
                preserved_initial_metadata=str(provenance.resolve()),sha256=sha(provenance)))
        else:self.evidence.append(dict(section="sensitivity_manifest",selected="output_hashes",reason="Native execution final manifest"))
        for name,expected in final_hashes.items():
            self.check(sha(p/name)==expected,"Sensitivity declared hash:"+name)
        selection=self.read_csv(p/"sensitivity_selection.csv")
        fac=self.subsets(self.read_csv(p/"sensitivity_facilities.csv"),["case","method","radius_km"])
        muni=self.subsets(self.read_csv(p/"sensitivity_municipal.csv"),["case","method","radius_km"])
        diag=self.subsets(self.read_csv(p/"sensitivity_network_diagnostics.csv"),["case","method","radius_km"])
        assignments={}
        for path in sorted((p/"networks").glob("*_assignments.csv")):
            frame=self.read_csv(path)
            tag=tuple(frame.iloc[0][c] for c in ("case","method","radius_km"))
            self.check(tag not in assignments,"Unique sensitivity network:"+str(tag));assignments[tag]=frame
        self.sensitivity_external={}
        for path in sorted((p/"networks").glob("*_external_segments.csv")):
            frame=self.read_csv(path)
            if frame.empty:continue
            tag=tuple(frame.iloc[0][c] for c in ("case","method","radius_km"))
            self.check(tag not in self.sensitivity_external,"Unique external-segment artifact:"+str(tag))
            self.sensitivity_external[tag]=frame
        cohorts={"main":(self.demand,self.orders)}
        for name in ("D16","D22"):
            cohorts[name]=(self.demand_frame(p/(name+"_postal_demand.csv")),self.read_csv(p/(name+"_order_origin.csv")))
        verified_cases=set()
        for row in selection.to_dict("records"):
            tag=(row["case"],row["method"],float(row["radius_km"]))
            key="sensitivity:"+":".join(map(str,tag))
            demand,orders=cohorts[row["cohort"]]
            demand=self.sensitivity_coordinates(demand,row["estimator"],meta)
            main_positions=postal_candidate_positions(self.demand,"J300",self.union)
            positions=postal_candidate_positions(demand,row["case"],self.union,self.demand.CEP.iloc[main_positions].tolist())
            evaluation_metric=row.get("evaluation_metric",row["metric"])
            if pd.isna(evaluation_metric):evaluation_metric=row["metric"]
            if row["case"] not in verified_cases:
                exported_path=p/("demand_"+row["case"]+".csv")
                if exported_path.exists():
                    exported=self.demand_frame(exported_path)
                    self.check(set(exported.CEP)==set(demand.CEP),key+": exported case demand membership")
                    exported=exported.set_index("CEP").reindex(demand.CEP)
                    self.check(np.array_equal(exported.n_pedidos,demand.n_pedidos),key+": exported case weights")
                    self.check(np.allclose(exported[["lat","lng"]],demand[["lat","lng"]],rtol=0,atol=TOL_DEG),key+": exported case coordinates")
                else:self.warnings.append("No explicit case-demand export for "+row["case"]+"; coordinates reconstructed from sources")
                verified_cases.add(row["case"])
            if "candidate_prefixes_sha256" in row and pd.notna(row["candidate_prefixes_sha256"]):
                actual=hashlib.sha256(json.dumps(demand.CEP.iloc[positions].tolist(),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
                self.check(actual==row["candidate_prefixes_sha256"],key+": declared candidate identities and order")
            if row["status"]=="structurally_infeasible":
                D=distance_matrix(demand[["lat","lng"]],demand[["lat","lng"]].iloc[positions],evaluation_metric)
                ceiling=int(demand.n_pedidos.to_numpy()[(D<=tag[2]).any(axis=1)].sum())
                self.compare(row["ceiling_orders"],ceiling,key+": independent structural ceiling",0)
                self.check(ceiling<(95*int(demand.n_pedidos.sum())+99)//100,key+": independent structural infeasibility")
                continue
            if row["status"]!="selected":
                self.check(False,key+": unresolved non-selected status","selected/structurally_infeasible",row["status"])
                continue
            if row["method"] in ("P-Median","MCLP"):row["_candidate_positions"]=positions
            city="municipality_for_sensitivity" if "municipality_for_sensitivity" in orders else "city_norm"
            self.check(tag in assignments,key+": assignment artifact present")
            if tag not in assignments:continue
            summary=diag[tag].iloc[0].to_dict() if tag in diag else {}
            metrics=self.network(key,{**summary,**row},demand,orders,fac[tag],assignments[tag],evaluation_metric,muni.get(tag),city)
            self.check(metrics["target_met"],key+": selected feasible")
            if tag in diag:
                self.compare_metrics(summary,metrics,key+":diagnostics")
                inside=self.inside(fac[tag].sort_values("facility_id")[["lat","lng"]])
                self.compare(summary["outside_union_facilities"],int((~inside).sum()),key+":diagnostics geography",0)
            self.verify_external_segments(key,row,demand,fac[tag],assignments[tag],summary,p)
            redistributed=fractional_redistribution(self.retained_raw_records(meta),demand,
                           fac[tag].sort_values("facility_id")[["lat","lng"]].to_numpy(float),tag[2],evaluation_metric)
            for field,value in redistributed.items():
                self.compare(summary[field],value,key+":"+field,TOL_KM)
        self.evidence.append(dict(section="sensitivity",rows=len(selection),complete=meta["complete"],
                                 coordinates="median/dedup_full reconstructed independently from hashed raw retained records"))
        self.verify_seed_windows(p)

    def verify_seed_windows(self,folder):
        path=folder/"seed30_fits.csv"
        if not path.exists():
            self.pending.append("30-seed sensitivity window absent");return
        fits=self.read_csv(path)
        recalculated=[];fit_cache={}
        self.check(len(fits)==1023,"Expected 1,023 seed-window evaluations",1023,len(fits))
        for row in fits.to_dict("records"):
            key="seed_window:R"+str(row["radius_km"])+":K"+str(row["K"])+":seed"+str(row["seed"])
            checkpoint=str(row["checkpoint"])
            if checkpoint not in fit_cache:
                file=folder/"checkpoints"/(checkpoint+".npz")
                self.files[str(file.resolve())]=sha(file)
                with np.load(file,allow_pickle=False) as artifact:
                    centers=artifact["centers"];labels=artifact["labels"]
                self.check(len(centers)==int(row["K"]),key+": checkpoint K")
                self.check(len(labels)==len(self.demand),key+": native label length")
                distances=distance_matrix(self.demand[["lat","lng"]],centers)
                nearest=distances.argmin(axis=1)
                native=distances[np.arange(len(self.demand)),labels]
                fit_cache[checkpoint]=(distances.min(axis=1),native,labels!=nearest)
            d,native,changed=fit_cache[checkpoint]
            met=recalculate_metrics(d,self.demand.n_pedidos,row["radius_km"])
            self.compare_metrics(row,met,key)
            self.compare(row["native_max_km"],native.max(),key+": native maximum")
            self.compare(row["reassigned_prefixes"],int(changed.sum()),key+": reassigned prefixes",0)
            self.compare(row["reassigned_orders"],int(self.demand.n_pedidos.to_numpy()[changed].sum()),key+": reassigned orders",0)
            recalculated.append(dict(radius_km=row["radius_km"],K=int(row["K"]),seed=int(row["seed"]),**met))
        independent=pd.DataFrame(recalculated)
        summaries=self.read_csv(folder/"seed30_by_K.csv")
        individuals=self.read_csv(folder/"seed30_by_seed.csv")
        for radius,group in independent[independent.seed.ne(42)].groupby("radius_km"):
            self.check(set(group.seed)==set(range(30)),"Thirty seeds R"+str(radius))
            all_groups=list(group.groupby("K",sort=True))
            simultaneous=next((int(k) for k,g in all_groups if g.target_met.all()),None)
            for k,g in all_groups:
                exported=summaries[(summaries.radius_km==radius)&(summaries.K==k)].iloc[0]
                self.compare(exported.n_seeds,30,"Seed summary count",0)
                self.compare(exported.feasible_seeds,int(g.target_met.sum()),"Seed summary feasible count",0)
                self.compare(exported.feasible_fraction,float(g.target_met.mean()),"Seed summary fraction",TOL_PCT)
                for source,target in (("coverage_pct","coverage"),("p95_empirical_km","p95"),("p99_empirical_km","p99"),("max_distance_km","max")):
                    unit="pct" if source=="coverage_pct" else "km"
                    self.compare(exported[target+"_min_"+unit],float(g[source].min()),"Seed summary "+target+" min")
                    self.compare(exported[target+"_max_"+unit],float(g[source].max()),"Seed summary "+target+" max")
                self.compare(exported.first_simultaneous_K_within_window,simultaneous,"Final seed-window simultaneous minimum",0)
            for seed,g in group.groupby("seed"):
                g=g.sort_values("K");exported=individuals[(individuals.radius_km==radius)&(individuals.seed==seed)].iloc[0]
                viable=g[g.target_met]
                first=int(viable.K.iloc[0]) if len(viable) else None
                self.compare(exported.first_feasible_K_within_window,first,"Seed individual first feasible K",0)
                self.compare(exported.left_censored,bool(g.target_met.iloc[0]),"Seed window left-censoring")
                regression=int((g.target_met.to_numpy()[:-1]&~g.target_met.to_numpy()[1:]).sum())
                self.compare(exported.feasible_to_infeasible_regressions,regression,"Seed feasibility reversals",0)
                self.compare(exported.first_simultaneous_K_within_window,simultaneous,"Seed simultaneous minimum",0)
        self.evidence.append(dict(section="seed_windows",rows=len(fits),independent_checkpoint_center_evaluations=len(fit_cache),
                                 limitation="Centers and native labels are artifact inputs; no retraining or second implementation of K-means"))

    def verify_external_segments(self,key,row,demand,facilities,assignment,summary,folder):
        ordered=facilities.sort_values("facility_id")
        centers=ordered[["lat","lng"]].to_numpy(float)
        assigned=assignment.set_index("CEP").reindex(demand.CEP)
        nearest=assigned.nearest_facility.to_numpy(int)
        starts=demand[["lng","lat"]].to_numpy(float)
        ends=centers[nearest,::-1]
        outside=shapely.difference(shapely.linestrings(np.stack([starts,ends],axis=1)),self.union)
        transform=Transformer.from_crs("EPSG:4326","EPSG:31983",always_xy=True)
        def projected(xy):
            x,y=transform.transform(xy[:,0],xy[:,1]);return np.column_stack([x,y])
        lengths=shapely.length(shapely.transform(outside,projected))/1000
        if "orders_external_segment_gt2km" in summary:
            self.compare(summary["orders_external_segment_gt2km"],int(demand.n_pedidos.to_numpy()[lengths>2].sum()),key+": external projected segment orders",0)
        tag=(row["case"],row["method"],float(row["radius_km"]))
        if tag in self.sensitivity_external:
            exported=self.sensitivity_external[tag].set_index("CEP")
            expected=pd.Series(lengths,index=demand.CEP)
            self.check(set(demand.CEP[lengths>TOL_KM]).issubset(set(exported.index)),key+": external segment membership")
            self.check(np.allclose(exported.external_union_segment_km_projected,expected.reindex(exported.index),rtol=1e-9,atol=TOL_KM),key+": external projected segment lengths")
            return
        self.check(not np.any(lengths>TOL_KM),key+": external segment artifact required")

    def validate_figures(self):
        path=self.args.main_dir/"figure_map_extremes_v22.csv"
        if not path.exists():
            self.pending.append("Figure three-extremes CSV absent");return
        extremes=self.read_csv(path)
        for tag,group in self.subsets(extremes,["scope","method","radius_km"]).items():
            tag=(tag[0],tag[1],float(tag[2]))
            key="main:"+":".join(map(str,tag))
            cached=self.cache[key];df=cached["demand"];d=cached["distances"]
            expected=np.argsort(-d,kind="stable")[:3]
            self.check(len(group)==3,"Figure "+key+": three extremes",3,len(group))
            self.check(list(group.CEP)==list(df.CEP.iloc[expected]),"Figure "+key+": top three prefixes",
                       list(df.CEP.iloc[expected]),list(group.CEP))
            pos=dict(zip(df.CEP,range(len(df))))
            for row in group.to_dict("records"):
                i=pos[row["CEP"]];fid=int(row["facility_id"]);f=cached["facilities"].iloc[fid]
                self.compare(row["distance_km"],d[i],"Figure "+key+":"+row["CEP"]+": distance")
                self.compare(row["orders"],df.n_pedidos.iloc[i],"Figure "+key+":"+row["CEP"]+": demand",0)
                self.compare(row["K"],len(cached["facilities"]),"Figure "+key+":"+row["CEP"]+": K",0)
                self.compare(row["lat"],df.lat.iloc[i],"Figure "+key+":"+row["CEP"]+": latitude",TOL_DEG)
                self.compare(row["lng"],df.lng.iloc[i],"Figure "+key+":"+row["CEP"]+": longitude",TOL_DEG)
                self.compare(row["facility_lat"],f.lat,"Figure "+key+":"+row["CEP"]+": facility latitude",TOL_DEG)
                self.compare(row["facility_lng"],f.lng,"Figure "+key+":"+row["CEP"]+": facility longitude",TOL_DEG)
                self.check(fid==int(cached["reported_nearest"][i]),"Figure "+key+":"+row["CEP"]+": facility ID")
        self.evidence.append(dict(section="figures",map_panels=len(self.subsets(extremes,["scope","method","radius_km"])),extremes=len(extremes)))
        native_path=self.args.main_dir/"figure_native_examples_v22.csv"
        if native_path.exists():
            examples=self.read_csv(native_path)
            for method,group in examples.groupby("method",sort=False):
                cached=self.cache["main:main:"+method+":3.0"]
                d=cached["distances"];native=cached["native"]
                changed=np.flatnonzero(cached["native_labels"]!=cached["reported_nearest"])
                ids=changed[np.argsort(-(native[changed]-d[changed]),kind="stable")[:3]]
                self.check(list(group.CEP)==list(cached["demand"].CEP.iloc[ids]),"Figure native:"+method+": three largest reductions")
                for i,row in zip(ids,group.to_dict("records")):
                    self.compare(row["reduction_km"],native[i]-d[i],"Figure native:"+method+":"+row["CEP"])

    def run_benchmark(self):
        if self.args.skip_benchmark:
            self.pending.append("Independent MILP benchmark explicitly skipped");return
        df=self.demand
        positions=np.asarray(sorted(range(len(df)),key=lambda i:(-int(df.n_pedidos.iloc[i]),df.CEP.iloc[i]))[:300])
        self.benchmark=independent_cover_benchmark(df[["lat","lng"]],df.n_pedidos,positions,time_limit=self.args.benchmark_time_limit)
        expected=next(n for n in self.networks if n["key"]=="exact:partial_J300_R5")
        self.check(self.benchmark["status"]==0 and self.benchmark.get("primal_verified",False),
                   "Independent partial-cover MILP certified optimum")
        if self.benchmark["K"] is not None:self.compare(self.benchmark["K"],expected["K"],"Independent partial-cover K",0)
        if self.benchmark["gap"] is not None:self.check(abs(self.benchmark["gap"])<=1e-8,"Independent MILP gap")
        self.benchmark["limitation"]="Independent model assembly and code, same installed SciPy/HiGHS solver; no cross-solver confirmation"
        self.benchmark["alternative_solver_inventory"]=dict(
            modules={name:importlib.util.find_spec(name) is not None for name in ("pulp","ortools","mip","cvxpy","highspy")},
            external_commands={name:shutil.which(name) for name in ("cbc","glpsol","scip")})

    def save(self, started):
        changed=[p for p,expected in self.files.items() if not Path(p).exists() or sha(p)!=expected]
        self.check(not changed,"Read inputs unchanged throughout independent verification",[],changed)
        status="failed" if self.failures else ("incomplete" if self.pending else "passed")
        report=dict(status=status,complete=not self.pending,failures=self.failures,warnings=self.warnings,
            pending=self.pending,checks=self.check_count,network_count=len(self.networks),
            networks=self.networks,evidence=self.evidence,independent_benchmark=self.benchmark,
            input_sha256=self.files,verifier_sha256=sha(__file__),
            tolerances=dict(distance_km_abs=TOL_KM,coordinate_degrees_abs=TOL_DEG,
                            percentage_points_abs=TOL_PCT,relative=1e-9,integer_counts=0,
                            coverage_boundary="Exact d <= R; no coverage tolerance",
                            quantiles="Weighted empirical inverse CDF at ceil(q*N); rational integer rank"),
            environment=dict(python=platform.python_version(),
                packages={name:importlib.metadata.version(name) for name in ("numpy","pandas","scipy","pyproj","shapely")}),
            limitations=["No repository modules imported; source artifacts are inputs, not instructions.",
              "Administrative union only: flags do not certify dry land, water crossings, road access or commercial eligibility.",
              "Does not independently refit every cluster search K; exported curves support enumeration checks.",
              "Same installed SciPy/HiGHS solver for independently assembled benchmark; not a second solver.",
              "No proof that centroid distances equal individual-address distances or operational routes.",
              "Raw-geolocation reconstruction checks estimator outputs, not factual address correctness."],
            elapsed_s=time.perf_counter()-started)
        out=self.args.out_dir;out.mkdir(parents=True,exist_ok=True)
        (out/"independent_validation.json").write_text(json.dumps(clean(report),ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        lines=["# Verificação independente v22","",f"Estado: **{status.upper()}**. Redes recalculadas: {len(self.networks)}. Verificações: {self.check_count}.",
               "",f"Falhas: {len(self.failures)}; pendências: {len(self.pending)}.","",
               "Os cálculos foram reimplementados sem importar módulos do repositório. Cobertura usa d ≤ R e os percentis empíricos usam o posto inteiro ceil(q×N).",
               "",f"Tolerâncias: distâncias {TOL_KM:g} km absolutos; coordenadas {TOL_DEG:g} graus; percentuais {TOL_PCT:g} pontos; contagens inteiras sem tolerância.",""]
        if self.pending:lines+=["## Pendências",""]+["- "+x for x in self.pending]+[""]
        if self.failures:lines+=["## Falhas",""]+["- "+json.dumps(clean(x),ensure_ascii=False) for x in self.failures]+[""]
        if self.benchmark:lines+=["## Benchmark independente","",json.dumps(clean(self.benchmark),ensure_ascii=False,indent=2),"",
                    "O modelo foi montado de forma independente, mas usa o mesmo SciPy/HiGHS disponível. Isso confirma a implementação e não constitui validação por um segundo solver.",""]
        lines+=["## Limitações",""]+["- "+x for x in report["limitations"]]+["",
                   "Hashes dos arquivos lidos, métricas por rede, evidências e ambiente estão registrados no JSON. Nenhum input foi alterado."]
        (out/"independent_validation.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        print(json.dumps(dict(status=status,complete=report["complete"],failures=len(self.failures),pending=self.pending,
                              networks=len(self.networks),checks=self.check_count,out=str(out)),ensure_ascii=False),flush=True)
        return 1 if self.failures else (2 if self.pending else 0)


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(x) for x in value]
    if isinstance(value,np.ndarray):return clean(value.tolist())
    if isinstance(value,(np.integer,np.floating,np.bool_)):return clean(value.item())
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=ROOT/"data")
    parser.add_argument("--main-dir",type=Path,default=ROOT/"data/v22_main")
    parser.add_argument("--exact-dir",type=Path,default=ROOT/"data/v22_exact")
    parser.add_argument("--sensitivity-dir",type=Path,default=ROOT/"data/v22_sensitivity")
    parser.add_argument("--out-dir",type=Path,default=ROOT/"data/v22_independent")
    parser.add_argument("--skip-benchmark",action="store_true",help="Diagnostic subset; report remains incomplete")
    parser.add_argument("--benchmark-time-limit",type=float,default=300.)
    args=parser.parse_args()
    if args.out_dir.resolve() in {p.resolve() for p in (args.data_dir,args.main_dir,args.exact_dir,args.sensitivity_dir)}:
        parser.error("Verification output must be separate from source directories")
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        parser.error("Use a fresh empty output directory; reports are not overwritten")
    auditor=Auditor(args);started=time.perf_counter()
    for name in ("load","validate_main","validate_exact","validate_sensitivity","validate_figures","run_benchmark"):
        try:getattr(auditor,name)()
        except Exception as error:
            auditor.failures.append(dict(check=name,exception=type(error).__name__,message=str(error)))
    raise SystemExit(auditor.save(started))


if __name__=="__main__":
    main()
