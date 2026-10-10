"""Adversarial tests of v23 profile interpretation and retained primal checks."""
import importlib.util
from itertools import combinations
from pathlib import Path
import unittest
import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]/"scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("module_"+name, SCRIPTS/(name+".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = load("13_certify_service_profiles_v23")
verifier = load("14_verify_service_profiles_v23")


class ServiceProfilesTests(unittest.TestCase):
    def test_count_and_closeness_against_exhaustive_subsets(self):
        D = np.array([[0., 4., 10.], [2., 0., 6.], [8., 4., 0.], [12., 8., 4.]])
        weights = np.array([40, 40, 19, 1])
        for T in (None, 5.):
            with self.subTest(maximum=T):
                brute = None
                for K in range(1, 4):
                    if any(weights[D[:, chosen].min(axis=1) <= 3].sum() >= 95
                           and (T is None or D[:, chosen].min(axis=1).max() <= T)
                           for chosen in combinations(range(3), K)):
                        brute = K
                        break
                certificate, arrays = producer.solve_count(D, weights, 3., T, 10.)
                self.assertEqual(certificate["K"], brute)
                self.assertTrue(certificate["solver_certified_optimal"])
                self.assertTrue(all(verifier.primal_checks(D, weights, arrays["primal_y"], arrays["primal_z"],
                                                          arrays["selected_indices"], 3., T, certificate).values()))

    def test_independent_primal_rejects_impossible_coverage(self):
        D = np.array([[0., 5.], [5., 0.]])
        w = np.array([50, 50])
        certificate = {"primal_objective": 1., "status": 0, "success": True, "mip_gap": 0., "dual_bound": 1.}
        checks = verifier.primal_checks(D, w, np.array([1., 0.]), np.ones(2), np.array([0]), 1., None, certificate)
        self.assertFalse(checks["covered_linking_constraints"])

    def test_independent_primal_rejects_fractional_opening(self):
        D = np.zeros((2, 2)); w = np.array([50, 50])
        certificate = {"primal_objective": 1., "status": 0, "success": True, "mip_gap": 0., "dual_bound": 1.}
        checks = verifier.primal_checks(D, w, np.array([.6, .4]), np.ones(2), np.array([0]), 1., None, certificate)
        self.assertFalse(checks["binary_facilities"])

    def test_K_max_dominance_does_not_imply_mean_P99_or_territorial_dominance(self):
        b = {"K": 80, "weighted_avg_distance_km": 1.6, "median_empirical_km": 1.5,
             "p95_empirical_km": 3., "p99_empirical_km": 4.3, "max_distance_km": 8.48,
             "municipalities_zero": 1, "municipalities_below80": 2, "covered_orders": 9216}
        a = dict(b, K=67, weighted_avg_distance_km=1.86, p99_empirical_km=6.71,
                 max_distance_km=7.96, municipalities_below80=5, covered_orders=9211)
        flags = producer.comparison_metrics(a, b)
        self.assertTrue(flags["dominates_K_max"])
        self.assertFalse(flags["dominates_K_mean_max"])
        self.assertFalse(flags["dominates_all_recorded_metrics"])

    def test_equal_K_and_max_can_still_improve_only_mean(self):
        b = {"K": 80, "weighted_avg_distance_km": 2., "median_empirical_km": 1.5,
             "p95_empirical_km": 3., "p99_empirical_km": 4.3, "max_distance_km": 8.48,
             "municipalities_zero": 1, "municipalities_below80": 2, "covered_orders": 9216}
        a = dict(b, weighted_avg_distance_km=1.6)
        flags = producer.comparison_metrics(a, b)
        self.assertFalse(flags["dominates_K_max"])
        self.assertTrue(flags["dominates_all_recorded_metrics"])

    def test_weighted_ranks_have_exact_integer_coverage_target(self):
        d, w = np.array([0., 1., 8.]), np.array([50, 44, 5])
        self.assertEqual(producer.required(99), 95)
        self.assertEqual(verifier.weighted_rank(d, w, 95, 100), 8.)
        self.assertEqual(producer.empirical(d, w, 95, 100), 8.)

    def test_independent_haversine_and_identical_coordinate_distance(self):
        coords = np.array([[-22.9, -43.2], [-23., -43.1], [-22.8, -43.3]])
        self.assertTrue(np.allclose(producer.distance_matrix(coords, coords),
                                    verifier.distances_to_centres(coords, coords), rtol=1e-12, atol=1e-10))
        self.assertTrue(np.array_equal(np.diag(verifier.distances_to_centres(coords, coords)), np.zeros(3)))


if __name__ == "__main__":
    unittest.main()
