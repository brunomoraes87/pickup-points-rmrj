"""Finite facility-location MILPs solved by SciPy/HiGHS.

Certificates refer only to the supplied distance matrix and candidate set.
Returned assignments are recomputed to the nearest selected candidate; profiles
describe that particular optimum, not every optimum of the cardinality model.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
import time
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, csr_matrix, hstack, identity

EARTH_RADIUS_KM = 6371.0088


@dataclass
class ExactResult:
    certificate: dict
    selected_indices: np.ndarray
    nearest_facility: np.ndarray
    nearest_distances_km: np.ndarray

    @property
    def status(self):
        return self.certificate["status"]

    @property
    def objective(self):
        return self.certificate["primal_objective"]


def validated_weights(weights):
    raw = np.asarray(weights, dtype=float)
    if (raw.ndim != 1 or not len(raw) or not np.isfinite(raw).all()
            or (raw <= 0).any() or (raw != np.floor(raw)).any()
            or raw.sum() > 2**53):
        raise ValueError("Positive integer order counts with exact float total required")
    return raw.astype(np.int64)


def required_orders(total_orders, target_fraction=Fraction(95, 100)):
    q = target_fraction if isinstance(target_fraction, Fraction) else Fraction(str(target_fraction))
    if not 0 < q <= 1 or int(total_orders) != total_orders or total_orders <= 0:
        raise ValueError("Positive integer total and fraction in (0,1] required")
    return (int(total_orders)*q.numerator+q.denominator-1)//q.denominator


def haversine_distance_matrix(demand_coords, candidate_coords, chunk_rows=64):
    """Bounded-memory Haversine matrix for [latitude, longitude] pairs."""
    a, b = np.asarray(demand_coords, float), np.asarray(candidate_coords, float)
    for coords in (a, b):
        if (coords.ndim != 2 or coords.shape[1] != 2 or not len(coords)
                or not np.isfinite(coords).all()
                or (np.abs(coords[:, 0]) > 90).any() or (np.abs(coords[:, 1]) > 180).any()):
            raise ValueError("Finite nonempty latitude/longitude pairs in bounds required")
    if not isinstance(chunk_rows, (int, np.integer)) or chunk_rows <= 0:
        raise ValueError("chunk_rows must be a positive integer")
    a, b = np.radians(a), np.radians(b)
    output = np.empty((len(a), len(b)), dtype=float)
    for first in range(0, len(a), chunk_rows):
        rows = a[first:first+chunk_rows]
        h = (np.sin((b[None, :, 0]-rows[:, None, 0])/2)**2
             + np.cos(rows[:, None, 0])*np.cos(b[None, :, 0])
             * np.sin((b[None, :, 1]-rows[:, None, 1])/2)**2)
        output[first:first+chunk_rows] = 2*EARTH_RADIUS_KM*np.arcsin(np.sqrt(np.clip(h, 0, 1)))
    return output


def empirical_percentile(distances, weights, probability):
    counts = validated_weights(weights)
    distances = np.asarray(distances, float)
    if distances.shape != counts.shape or not np.isfinite(distances).all() or (distances < 0).any():
        raise ValueError("Distances must be finite, nonnegative and match demand")
    order = np.argsort(distances, kind="stable")
    rank = required_orders(int(counts.sum()), probability)
    return float(distances[order[np.searchsorted(np.cumsum(counts[order]), rank)]])


def _validate(distance_matrix, weights, time_limit, mip_rel_gap, radius=None, budget=None):
    counts = validated_weights(weights)
    distances = np.asarray(distance_matrix, dtype=float)
    if (distances.ndim != 2 or distances.shape[0] != len(counts)
            or distances.shape[1] == 0 or not np.isfinite(distances).all()
            or (distances < 0).any()):
        raise ValueError("Finite nonnegative n-demand by m-candidate distance matrix required")
    if not np.isfinite(time_limit) or time_limit <= 0 or not np.isfinite(mip_rel_gap) or mip_rel_gap < 0:
        raise ValueError("Positive time_limit and nonnegative mip_rel_gap required")
    if radius is not None and (not np.isfinite(radius) or radius <= 0):
        raise ValueError("Positive finite radius required")
    if budget is not None and (
            not isinstance(budget, (int, np.integer)) or budget < 0 or budget > distances.shape[1]):
        raise ValueError("Facility budget must be an integer in [0, candidate_count]")
    return distances, counts


def _metrics(distances, counts, radius, target):
    n = int(counts.sum())
    if not np.isfinite(distances).all():
        return {"covered_orders": 0 if radius is not None else None,
                "outside_orders": n if radius is not None else None,
                "coverage_pct": 0.0 if radius is not None else None,
                "target_met": False if radius is not None else None,
                "weighted_avg_distance_km": None, "median_empirical_km": None,
                "p95_empirical_km": None, "p99_empirical_km": None, "max_distance_km": None}
    covered = int(counts[distances <= radius].sum()) if radius is not None else None
    return {
        "covered_orders": covered, "outside_orders": n-covered if covered is not None else None,
        "coverage_pct": 100*covered/n if covered is not None else None,
        "target_met": covered >= target if covered is not None else None,
        "weighted_avg_distance_km": float(np.average(distances, weights=counts)),
        "median_empirical_km": empirical_percentile(distances, counts, Fraction(1, 2)),
        "p95_empirical_km": empirical_percentile(distances, counts, Fraction(95, 100)),
        "p99_empirical_km": empirical_percentile(distances, counts, Fraction(99, 100)),
        "max_distance_km": float(distances.max()),
    }


def _number(result, key):
    value = getattr(result, key, None)
    return None if value is None else float(value)


def _pack(result, distances, counts, problem, radius, target, solver_s, setup_s,
          budget=None, mandatory_radius=None, time_limit=300, mip_rel_gap=0):
    m, n = distances.shape[1], distances.shape[0]
    selected = np.flatnonzero(result.x[:m] > .5).astype(np.int64) if result.x is not None else np.array([], dtype=np.int64)
    if len(selected):
        local = distances[:, selected]
        nearest = local.argmin(axis=1).astype(np.int64)
        nearest_distances = local.min(axis=1)
    else:
        nearest = np.full(n, -1, dtype=np.int64)
        nearest_distances = np.full(n, np.nan)
    metrics = _metrics(nearest_distances, counts, radius, target)
    gap = _number(result, "mip_gap")
    objective = _number(result, "fun")
    dual = _number(result, "mip_dual_bound")
    feasible = result.x is not None
    if feasible:
        yerror = float(np.abs(result.x[:m]-np.round(result.x[:m])).max())
        feasible = yerror <= 1e-5 and (budget is None or len(selected) == budget)
        if problem == "partial_cover":
            feasible = feasible and metrics["covered_orders"] >= target
        if mandatory_radius is not None:
            feasible = feasible and np.all(nearest_distances <= mandatory_radius+1e-9)
        if problem == "pmedian":
            recomputed = float(np.sum(counts*nearest_distances)) if len(selected) else None
            feasible = feasible and recomputed is not None and abs(recomputed-objective) <= max(1e-5, abs(objective)*1e-8)
        elif problem == "maximal_cover":
            recomputed = -float(metrics["covered_orders"])
            feasible = feasible and abs(recomputed-objective) < 1e-4
        else:
            recomputed = float(len(selected))
            feasible = feasible and abs(recomputed-objective) < 1e-5
        if not feasible:
            raise RuntimeError("Returned primal fails independent facility/assignment feasibility verification")
    else:
        yerror, recomputed = None, None
    certificate = {
        "problem": problem, "solver": "HiGHS via scipy.optimize.milp",
        "status": int(result.status), "success": bool(result.success), "message": str(result.message),
        "primal_objective": objective, "dual_bound": dual, "mip_gap": gap,
        "mip_node_count": _number(result, "mip_node_count"),
        "solver_runtime_s": float(solver_s), "setup_runtime_s": float(setup_s),
        "time_limit_s": float(time_limit), "requested_mip_rel_gap": float(mip_rel_gap),
        "has_primal_solution": result.x is not None, "primal_verified": bool(feasible),
        "solver_certified_optimal": bool(result.status == 0 and feasible and gap is not None and gap <= 1e-8),
        "certified_infeasible": bool(result.status == 2),
        "n_demand_points": n, "n_candidates": m, "total_orders": int(counts.sum()),
        "required_orders": target, "radius_km": radius, "budget_K": budget,
        "mandatory_radius_km": mandatory_radius, "n_facilities": len(selected),
        "max_y_integrality_error": yerror, "independent_primal_objective": recomputed,
        "finite_candidate_space_only": True, **metrics,
    }
    if problem == "partial_cover" and feasible and dual is not None:
        certificate["integer_bound_matches_K"] = math.ceil(dual-1e-7) == len(selected)
    if problem == "maximal_cover" and dual is not None:
        certificate["covered_orders_upper_bound"] = -dual
    return ExactResult(certificate, selected, nearest, nearest_distances)


def solve_partial_cover(distance_matrix, weights, radius_km, mandatory_radius_km=None,
                        target_fraction=Fraction(95, 100), time_limit=300, mip_rel_gap=0):
    """Minimize opened facilities for the order-weighted partial coverage target.

    A mandatory radius adds coverage of every demand prefix within that radius.
    Continuous z_i in [0,1] cannot mark demand covered without an open neighbor.
    """
    entry = time.perf_counter()
    distances, counts = _validate(distance_matrix, weights, time_limit, mip_rel_gap, radius_km)
    if mandatory_radius_km is not None and (
            not np.isfinite(mandatory_radius_km) or mandatory_radius_km <= 0):
        raise ValueError("Positive finite mandatory radius required")
    n, m = distances.shape
    target = required_orders(int(counts.sum()), target_fraction)
    cov = distances <= radius_km
    ceiling = int(counts[cov.any(axis=1)].sum())
    if ceiling < target or (mandatory_radius_km is not None and
                           not (distances <= mandatory_radius_km).any(axis=1).all()):
        record = {
            "problem": "partial_cover", "solver": "structural candidate coverage bound",
            "status": 2, "success": False, "message": "Candidate set cannot meet required coverage/proximity",
            "primal_objective": None, "dual_bound": None, "mip_gap": None,
            "mip_node_count": None, "solver_runtime_s": 0.0, "setup_runtime_s": time.perf_counter()-entry,
            "time_limit_s": float(time_limit), "requested_mip_rel_gap": float(mip_rel_gap),
            "has_primal_solution": False, "primal_verified": False,
            "solver_certified_optimal": False, "certified_infeasible": True,
            "certificate_type": "candidate_coverage_ceiling", "candidate_ceiling_orders": ceiling,
            "n_demand_points": n, "n_candidates": m, "total_orders": int(counts.sum()),
            "required_orders": target, "radius_km": radius_km, "budget_K": None,
            "mandatory_radius_km": mandatory_radius_km, "n_facilities": 0,
            "finite_candidate_space_only": True,
        }
        return ExactResult(record, np.array([], dtype=np.int64), np.full(n, -1, dtype=np.int64), np.full(n, np.nan))
    constraints = [
        LinearConstraint(hstack([-csr_matrix(cov, dtype=float), identity(n, format="csr")], format="csr"), -np.inf, 0),
        LinearConstraint(csr_matrix(np.r_[np.zeros(m), counts.astype(float)][None, :]), target, np.inf),
    ]
    if mandatory_radius_km is not None:
        constraints.append(LinearConstraint(
            hstack([csr_matrix(distances <= mandatory_radius_km, dtype=float), csr_matrix((n, n))], format="csr"), 1, np.inf))
    c, integrality = np.r_[np.ones(m), np.zeros(n)], np.r_[np.ones(m), np.zeros(n)]
    setup_s = time.perf_counter()-entry
    started = time.perf_counter()
    result = milp(c, integrality=integrality, bounds=Bounds(0, 1), constraints=constraints,
                  options={"time_limit": time_limit, "mip_rel_gap": mip_rel_gap, "disp": False})
    packed = _pack(result, distances, counts, "partial_cover", radius_km, target, time.perf_counter()-started, setup_s,
                   mandatory_radius=mandatory_radius_km, time_limit=time_limit, mip_rel_gap=mip_rel_gap)
    packed.certificate["candidate_ceiling_orders"] = ceiling
    return packed


def solve_maximal_cover(distance_matrix, weights, K, radius_km,
                        target_fraction=Fraction(95, 100), time_limit=300, mip_rel_gap=0):
    """Maximize weighted radius coverage at an exact finite facility budget."""
    entry = time.perf_counter()
    distances, counts = _validate(distance_matrix, weights, time_limit, mip_rel_gap, radius_km, K)
    n, m = distances.shape
    cov = distances <= radius_km
    constraints = [
        LinearConstraint(hstack([-csr_matrix(cov, dtype=float), identity(n, format="csr")], format="csr"), -np.inf, 0),
        LinearConstraint(csr_matrix(np.r_[np.ones(m), np.zeros(n)][None, :]), K, K),
    ]
    c, integrality = np.r_[np.zeros(m), -counts.astype(float)], np.r_[np.ones(m), np.zeros(n)]
    setup_s = time.perf_counter()-entry
    started = time.perf_counter()
    result = milp(c, integrality=integrality, bounds=Bounds(0, 1), constraints=constraints,
                  options={"time_limit": time_limit, "mip_rel_gap": mip_rel_gap, "disp": False})
    packed = _pack(result, distances, counts, "maximal_cover", radius_km,
                   required_orders(int(counts.sum()), target_fraction), time.perf_counter()-started, setup_s,
                   budget=K, time_limit=time_limit, mip_rel_gap=mip_rel_gap)
    packed.certificate["candidate_ceiling_orders"] = int(counts[cov.any(axis=1)].sum())
    return packed


def solve_pmedian(distance_matrix, weights, K, evaluation_radius_km=None,
                  target_fraction=Fraction(95, 100), time_limit=300, mip_rel_gap=0):
    """Minimize weighted nearest-facility distance for exactly K candidates."""
    entry = time.perf_counter()
    distances, counts = _validate(distance_matrix, weights, time_limit, mip_rel_gap, evaluation_radius_km, K)
    if K == 0:
        raise ValueError("P-median requires at least one facility")
    n, m = distances.shape
    nx = n*m
    cells = np.arange(nx)
    assign_one = coo_matrix((np.ones(nx), (np.repeat(np.arange(n), m), m+cells)), shape=(n, m+nx)).tocsr()
    link = coo_matrix((np.r_[np.ones(nx), -np.ones(nx)],
        (np.r_[cells, cells], np.r_[m+cells, np.tile(np.arange(m), n)])), shape=(nx, m+nx)).tocsr()
    constraints = [
        LinearConstraint(assign_one, 1, 1), LinearConstraint(link, -np.inf, 0),
        LinearConstraint(csr_matrix(np.r_[np.ones(m), np.zeros(nx)][None, :]), K, K),
    ]
    c, integrality = np.r_[np.zeros(m), (counts[:, None]*distances).ravel()], np.r_[np.ones(m), np.zeros(nx)]
    setup_s = time.perf_counter()-entry
    started = time.perf_counter()
    result = milp(c, integrality=integrality, bounds=Bounds(0, 1), constraints=constraints,
                  options={"time_limit": time_limit, "mip_rel_gap": mip_rel_gap, "disp": False})
    return _pack(result, distances, counts, "pmedian", evaluation_radius_km,
                 required_orders(int(counts.sum()), target_fraction), time.perf_counter()-started, setup_s,
                 budget=K, time_limit=time_limit, mip_rel_gap=mip_rel_gap)
