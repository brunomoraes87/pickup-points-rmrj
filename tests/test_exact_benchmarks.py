"""Small MILPs checked against exhaustive subsets, plus canonical candidate rules."""
import importlib.util
from itertools import combinations
import json
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
from shapely.geometry import box

SCRIPTS = Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0, str(SCRIPTS))
from candidate_sets import (grid_candidates, inside_union_mask, select_candidate_indices)
from exact_benchmarks import (haversine_distance_matrix, required_orders, solve_maximal_cover,
                              solve_partial_cover, solve_pmedian)


def brute_partial(D, weights, radius, target, maximum=None):
    for k in range(1, D.shape[1]+1):
        for selected in combinations(range(D.shape[1]), k):
            d = D[:, selected].min(axis=1)
            if weights[d <= radius].sum() >= target and (maximum is None or np.all(d <= maximum)):
                return k
    return None


def brute_maximum(D, weights, radius, k):
    return max(int(weights[D[:, selected].min(axis=1) <= radius].sum())
               for selected in combinations(range(D.shape[1]), k))


def brute_pmedian(D, weights, k):
    return min(float(np.sum(weights*D[:, selected].min(axis=1)))
               for selected in combinations(range(D.shape[1]), k))


class ExhaustiveMILPTests(unittest.TestCase):
    def test_three_objectives_match_brute_force_with_unequal_order_weights(self):
        rng = np.random.default_rng(1984)
        for instance in range(4):
            n, m = 6, 5
            points, facilities = rng.uniform(0, 10, size=(n, 2)), rng.uniform(0, 10, size=(m, 2))
            D = np.sqrt(((points[:, None]-facilities[None, :])**2).sum(axis=2))
            weights = rng.integers(1, 12, size=n)
            radius = 3.8
            target = required_orders(int(weights.sum()))
            with self.subTest(instance=instance, problem="partial"):
                expected = brute_partial(D, weights, radius, target)
                result = solve_partial_cover(D, weights, radius)
                if expected is None:
                    self.assertEqual(result.status, 2)
                    self.assertTrue(result.certificate["certified_infeasible"])
                else:
                    self.assertTrue(result.certificate["solver_certified_optimal"])
                    self.assertEqual(len(result.selected_indices), expected)
                    self.assertAlmostEqual(result.objective, expected, places=7)
                    self.assertAlmostEqual(result.certificate["dual_bound"], expected, places=7)
            with self.subTest(instance=instance, problem="maximal"):
                result = solve_maximal_cover(D, weights, 2, radius)
                self.assertTrue(result.certificate["solver_certified_optimal"])
                self.assertEqual(result.certificate["covered_orders"],
                                 brute_maximum(D, weights, radius, 2))
            with self.subTest(instance=instance, problem="pmedian"):
                result = solve_pmedian(D, weights, 2, evaluation_radius_km=radius)
                self.assertTrue(result.certificate["solver_certified_optimal"])
                self.assertAlmostEqual(result.objective, brute_pmedian(D, weights, 2), places=7)

    def test_required_coverage_cannot_ignore_five_percent_rounding(self):
        D = np.array([[0., 20.], [20., 0.]])
        result = solve_partial_cover(D, [19, 2], 1)
        self.assertEqual(required_orders(9691), 9207)
        self.assertEqual(required_orders(21), 20)
        self.assertEqual(len(result.selected_indices), 2)
        self.assertEqual(result.certificate["covered_orders"], 21)

    def test_proximity_is_required_even_for_an_order_outside_global_95_percent(self):
        locations = np.array([0., 1., 2., 10.])
        D = np.abs(locations[:, None]-locations[None, :])
        weights = np.array([40, 40, 15, 5])
        ordinary = solve_partial_cover(D, weights, 2.1)
        protected = solve_partial_cover(D, weights, 2.1, mandatory_radius_km=3)
        self.assertEqual(len(ordinary.selected_indices), 1)
        self.assertEqual(len(protected.selected_indices), 2)
        self.assertGreater(ordinary.nearest_distances_km.max(), 3)
        self.assertLessEqual(protected.nearest_distances_km.max(), 3)
        self.assertEqual(len(protected.selected_indices),
                         brute_partial(D, weights, 2.1, 95, maximum=3))

    def test_candidate_ceiling_and_impossible_proximity_are_certified_before_solve(self):
        D = np.array([[0.], [10.]])
        impossible = solve_partial_cover(D, [1, 1], 1)
        self.assertEqual(impossible.status, 2)
        self.assertEqual(impossible.certificate["candidate_ceiling_orders"], 1)
        self.assertEqual(impossible.certificate["solver_runtime_s"], 0)
        proximity = solve_partial_cover(D, [95, 5], 1, mandatory_radius_km=2)
        self.assertEqual(proximity.status, 2)

    def test_zero_budget_maximal_cover_and_invalid_parameters(self):
        result = solve_maximal_cover(np.array([[0., 5.], [5., 0.]]), [3, 2], 0, 1)
        self.assertEqual(result.objective, 0)
        self.assertEqual(result.certificate["covered_orders"], 0)
        self.assertEqual(len(result.selected_indices), 0)
        for kwargs in ({"K": 3}, {"K": 1.2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                solve_maximal_cover([[0., 1.]], [1], radius_km=1, **kwargs)
        with self.assertRaises(ValueError):
            solve_partial_cover([[0., np.nan]], [1], 1)
        with self.assertRaises(ValueError):
            solve_pmedian([[0., 1.]], [1], 0)
        with self.assertRaises(ValueError):
            solve_partial_cover([[0.], [1.]], [1, 0], 1)

    def test_returned_assignments_independently_match_chosen_facilities(self):
        D = np.array([[0., 3., 10.], [2., 1., 8.], [9., 8., 0.]])
        weights = np.array([5, 10, 1])
        for result in (solve_partial_cover(D, weights, 2),
                       solve_pmedian(D, weights, 1, evaluation_radius_km=2),
                       solve_maximal_cover(D, weights, 2, 2)):
            expected = D[:, result.selected_indices].min(axis=1)
            np.testing.assert_allclose(result.nearest_distances_km, expected)
            self.assertEqual(int(weights[expected <= 2].sum()), result.certificate["covered_orders"])


class CandidateRuleTests(unittest.TestCase):
    def test_positions_ignore_input_index_labels_and_reverse_only_the_ties(self):
        demand = pd.DataFrame({"CEP": ["20003", "20001", "20002", "20004"],
                               "n_pedidos": [10, 10, 20, 1]}, index=[8, 12, 2, 40])
        before = demand.copy(deep=True)
        np.testing.assert_array_equal(select_candidate_indices(demand, 2), [2, 1])
        np.testing.assert_array_equal(select_candidate_indices(demand, 2, "descending"), [2, 0])
        np.testing.assert_array_equal(select_candidate_indices(demand, 10), [2, 1, 0, 3])
        pd.testing.assert_frame_equal(demand, before)

    def test_eligibility_changes_candidates_without_dropping_demand(self):
        demand = pd.DataFrame({"customer_zip_code_prefix": [20001, 20002, 20003],
                               "n_pedidos": [20, 10, 1]})
        before = demand.copy(deep=True)
        result = select_candidate_indices(demand, 2, eligible_mask=[False, True, True])
        np.testing.assert_array_equal(result, [1, 2])
        self.assertEqual(demand.n_pedidos.sum(), 31)
        pd.testing.assert_frame_equal(demand, before)
        with self.assertRaises(ValueError):
            select_candidate_indices(demand, 2, eligible_mask=[True, False])
        with self.assertRaises(ValueError):
            select_candidate_indices(demand, 2, tie_order="random")

    def test_canonical_actual_J300_is_identical_in_membership_and_order_to_v21(self):
        data = SCRIPTS.parent/"data"
        demand = pd.read_csv(data/"demanda_por_cep.csv", dtype={"customer_zip_code_prefix": str})
        metadata = json.loads((data/"service_selection/service_metadata.json").read_text(encoding="utf-8"))
        selected = select_candidate_indices(demand, 300)
        legacy = demand.nlargest(300, "n_pedidos").index.to_numpy()
        np.testing.assert_array_equal(selected, legacy)
        np.testing.assert_array_equal(selected, metadata["protocol"]["candidate_indices"])
        self.assertEqual(selected.dtype.kind, "i")

    def test_grid_filter_changes_only_facility_space_and_all_retained_candidates_are_inside(self):
        demand = pd.DataFrame({
            "CEP": ["20001", "20002", "20003"], "n_pedidos": [20, 10, 1],
            "lat": [-22.9, -22.9, -22.9], "lng": [-43.2, -43.19, -43.17]})
        before = demand.copy(deep=True)
        union = box(-43.205, -22.905, -43.18, -22.895)
        hybrid, meta = grid_candidates(demand, union, 500, filter_postal=False)
        strict, filtered = grid_candidates(demand, union, 500, filter_postal=True)
        self.assertEqual(meta["postal_outside_before_filter"], 1)
        self.assertEqual(len(hybrid)-len(strict), 1)
        self.assertTrue(strict.inside_union.all())
        self.assertEqual(filtered["postal_candidates"], 2)
        self.assertEqual(demand.n_pedidos.sum(), 31)
        pd.testing.assert_frame_equal(demand, before)
        self.assertTrue(inside_union_mask(strict[["lat", "lng"]].to_numpy(), union).all())

    def test_haversine_bounds_and_same_location_are_independent_of_candidate_order(self):
        points = np.array([[-22.9, -43.2], [-22.91, -43.21]])
        forward = haversine_distance_matrix(points, points)
        reverse = haversine_distance_matrix(points, points[::-1])
        np.testing.assert_allclose(np.diag(forward), [0, 0])
        np.testing.assert_allclose(forward[:, ::-1], reverse)
        self.assertGreater(forward[0, 1], 1)
        with self.assertRaises(ValueError):
            haversine_distance_matrix([[91, 0]], points)


if __name__ == "__main__":
    unittest.main()
