"""Analytical and small synthetic checks of the matched-service K protocol."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "service_selection", SCRIPTS / "05_select_service_k.py")
service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = service
spec.loader.exec_module(service)
from methods import EARTH_R_KM, haversine_pairwise, haversine_to_centers, method_mclp_heuristic


def line_demand(distances, orders):
    return pd.DataFrame({
        "CEP": [f"{index:05d}" for index in range(len(distances))],
        "lat": np.zeros(len(distances)),
        "lng": np.asarray(distances) * 180 / (np.pi * EARTH_R_KM),
        "n_pedidos": orders, "city_norm": ["test"] * len(distances),
    })


class EmpiricalCoverageTests(unittest.TestCase):
    def test_exact_required_order_count_for_study(self):
        self.assertEqual(service.required_orders(9691), 9207)
        self.assertEqual(service.required_orders(20), 19)
        self.assertEqual(service.required_orders(21), 20)

    def test_empirical_p95_is_equivalent_to_coverage_not_linear_interpolation(self):
        result = service.radius_metrics([1, 3.1], [19, 1], 1)
        self.assertTrue(result["target_met"])
        self.assertEqual(result["p95_empirical_km"], 1)
        self.assertGreater(result["p95_linear_km"], 1)
        self.assertEqual(result["covered_orders"], 19)
        self.assertFalse(service.radius_metrics([1, 3.1], [18, 2], 1)["target_met"])

    def test_inverse_cdf_matches_expanded_numpy_for_ties_and_unequal_weights(self):
        distances, counts = [3, 0, 3, 20, 1], [11, 97, 5, 1, 8]
        expanded = np.repeat(distances, counts)
        for q in (.5, .95, .99, 1):
            with self.subTest(q=q):
                self.assertEqual(service.empirical_quantile(distances, counts, q),
                                 np.quantile(expanded, q, method="inverted_cdf"))
        for radius in (0.1, 1, 2, 3, 19, 20):
            result = service.radius_metrics(distances, counts, radius)
            self.assertEqual(result["target_met"], result["p95_empirical_km"] <= radius)

    def test_invalid_counts_are_rejected(self):
        for counts in ([1, 0], [1, 1.5], [1, np.nan], [1, -1]):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                service.radius_metrics([0, 1], counts, 1)


class ExhaustiveSelectionTests(unittest.TestCase):
    def test_first_integer_feasible_even_if_later_curve_regresses(self):
        rows = [{"K_target": k, "covered_orders": covered}
                for k, covered in enumerate([94, 96, 93, 98], start=1)]
        self.assertEqual(service.first_feasible_k(rows, 95), 2)
        self.assertEqual(service.first_feasible_k(list(reversed(rows)), 95), 2)

    def test_missing_smaller_k_cannot_be_claimed_as_minimum(self):
        with self.assertRaisesRegex(ValueError, "smaller integer"):
            service.first_feasible_k([
                {"K_target": 1, "covered_orders": 90},
                {"K_target": 3, "covered_orders": 96}], 95)

    def test_all_seeds_must_meet_target_at_same_k_not_at_any_previous_k(self):
        rows = []
        values = ([96, 94, 94, 94, 94], [94, 96, 96, 96, 96], [96] * 5)
        for k, coverages in enumerate(values, start=1):
            rows.extend({"K_target": k, "seed": seed, "covered_orders": coverage}
                        for seed, coverage in zip(service.SEEDS, coverages))
        self.assertEqual(service.first_feasible_k(rows, 95, seeds=service.SEEDS), 3)
        self.assertFalse(service.all_seeds_feasible(rows[:4], 95))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            service.all_seeds_feasible([rows[0], rows[0]], 95)

    def test_300_candidates_can_structurally_fail_before_any_fitting(self):
        distances = np.full((400, 400), 100.)
        np.fill_diagonal(distances, 0.)
        bound = service.candidate_coverage_ceiling(
            distances, np.ones(400), np.arange(300), 3)
        self.assertFalse(bound["target_met"])
        self.assertEqual(bound["covered_orders"], 300)
        self.assertEqual(bound["coverage_pct"], 75)
        self.assertTrue(service.candidate_coverage_ceiling(
            distances, np.ones(400), np.arange(400), 3)["target_met"])


class GreedyEquivalenceTests(unittest.TestCase):
    def test_every_mclp_prefix_matches_original_fit_including_ties_and_saturation(self):
        df = line_demand([0, 1, 2, 10, 11, 20], [4, 2, 4, 1, 1, 3])
        coords = df[["lat", "lng"]].to_numpy()
        distances = haversine_pairwise(coords[:, 0], coords[:, 1])
        candidates = np.array([4, 0, 5, 2, 1, 3])
        for radius in (0.1, 1.1, 30):
            chosen, cumulative = service.mclp_greedy_trajectory(
                distances, df.n_pedidos, candidates, radius)
            self.assertTrue(np.all(np.diff(cumulative) >= 0))
            for k in range(1, len(candidates) + 1):
                with self.subTest(radius=radius, k=k):
                    labels, centers, _ = method_mclp_heuristic(
                        df, k, radius, candidates_idx=candidates)
                    selected = chosen[:k]
                    np.testing.assert_array_equal(centers, coords[selected])
                    np.testing.assert_array_equal(labels, distances[:, selected].argmin(axis=1))


class AtomicCheckpointTests(unittest.TestCase):
    def test_two_transient_locks_retry_then_replace_json_and_csv(self):
        original_replace = Path.replace
        writers = (
            ("data.json", lambda path: service.atomic_json(path, {"value": 42})),
            ("data.csv", lambda path: service.atomic_csv(path, pd.DataFrame({"value": [42]}))),
        )
        for filename, writer in writers:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / filename
                destination.write_text("previous", encoding="utf-8")
                calls = []

                def replace_after_two_locks(temporary, target):
                    calls.append((temporary, target))
                    if len(calls) <= 2:
                        raise PermissionError("Synthetic Windows destination lock")
                    return original_replace(temporary, target)

                with patch.object(Path, "replace", autospec=True,
                                  side_effect=replace_after_two_locks), \
                        patch.object(service.time, "sleep") as sleep:
                    writer(destination)
                self.assertEqual(len(calls), 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [.05, .1])
                if filename.endswith(".json"):
                    self.assertEqual(json.loads(destination.read_text()), {"value": 42})
                else:
                    self.assertEqual(pd.read_csv(destination).value.tolist(), [42])

    def test_permanent_lock_has_bounded_retries_and_preserves_previous_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "data.json"
            destination.write_text("previous", encoding="utf-8")
            with patch.object(Path, "replace", autospec=True,
                              side_effect=PermissionError("Permanent lock")) as replace, \
                    patch.object(service.time, "sleep") as sleep:
                with self.assertRaisesRegex(PermissionError, "Permanent lock"):
                    service.atomic_json(destination, {"value": 42})
            self.assertEqual(replace.call_count, 6)
            self.assertEqual([call.args[0] for call in sleep.call_args_list],
                             [.05, .1, .2, .4, .8])
            self.assertEqual(destination.read_text(), "previous")
            self.assertTrue(destination.with_name("data.json.tmp").exists())

    def test_unrelated_io_error_propagates_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "data.csv"
            with patch.object(Path, "replace", autospec=True,
                              side_effect=OSError("Disk failure")) as replace, \
                    patch.object(service.time, "sleep") as sleep:
                with self.assertRaisesRegex(OSError, "Disk failure"):
                    service.atomic_csv(destination, pd.DataFrame({"value": [42]}))
            self.assertEqual(replace.call_count, 1)
            sleep.assert_not_called()

class ReproducibilityTests(unittest.TestCase):
    def test_cached_fit_survives_restart_and_signature_rejects_changed_protocol(self):
        df = line_demand([0, 2, 10, 11], [4, 3, 2, 1])
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "demand.csv"
            df.to_csv(path, index=False)
            first = service.ServiceSearch(df, path, base / "out",
                                          radii=[3], candidates=2, max_k=4)
            fitted = first.fit("main", "P-Median", 1, first.top)
            first.record("main", "P-Median", 3., 1, -1, fitted)
            first.save_snapshot()
            second = service.ServiceSearch(df, path, base / "out",
                                           radii=[3], candidates=2, max_k=4)
            with patch.object(service, "method_pmedian_heuristic",
                              side_effect=AssertionError("Cache should prevent a refit")):
                cached = second.fit("main", "P-Median", 1, second.top)
            np.testing.assert_array_equal(cached[0], fitted[0])
            np.testing.assert_array_equal(cached[1], fitted[1])
            self.assertEqual(cached[2], fitted[2])
            self.assertEqual(len(second.curves), 1)
            with self.assertRaisesRegex(ValueError, "signature"):
                service.ServiceSearch(df, path, base / "out",
                                      radii=[5], candidates=2, max_k=4)

    def test_small_complete_search_exports_only_selected_and_independently_correct_assignments(self):
        df = line_demand([0, 2, 10, 11], [4, 3, 2, 1])
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "demand.csv"
            df.to_csv(path, index=False)
            run = service.ServiceSearch(df, path, base / "out",
                                        radii=[1, 3], candidates=2, max_k=4)
            run.run()
            selection = pd.read_csv(base / "out" / "service_selection.csv")
            curves = pd.read_csv(base / "out" / "service_curves.csv")
            assignments = pd.read_csv(base / "out" / "service_assignments.csv", dtype={"CEP": str})
            facilities = pd.read_csv(base / "out" / "service_facilities.csv")
            self.assertEqual(len(selection), 16)  # 12 principal + four structural sensitivities.
            self.assertEqual((selection.status == "structurally_infeasible").sum(), 4)
            self.assertTrue((selection[selection.scope != "main"].status == "selected").all())
            for _, row in selection[selection.status == "selected"].iterrows():
                mask = ((curves.scope == row.scope) & (curves.method == row.method)
                        & (curves.radius_km == row.radius_km))
                prefix = curves[mask]
                seeds = service.SEEDS if row.method == "KMeans-weighted" else None
                self.assertEqual(service.first_feasible_k(
                    prefix.to_dict("records"), 10, seeds=seeds), row.K_selected)
                assigned = assignments[(assignments.scope == row.scope)
                                       & (assignments.method == row.method)
                                       & (assignments.radius_km == row.radius_km)]
                opened = facilities[(facilities.scope == row.scope)
                                    & (facilities.method == row.method)
                                    & (facilities.radius_km == row.radius_km)]
                D = haversine_to_centers(assigned.lat, assigned.lng, opened.lat, opened.lng)
                np.testing.assert_allclose(assigned.distance_km, D.min(axis=1), atol=1e-10)
                np.testing.assert_array_equal(assigned.outside_R, D.min(axis=1) > row.radius_km)
                self.assertEqual(int(assigned.loc[~assigned.outside_R, "n_pedidos"].sum()),
                                 row.covered_orders)
                self.assertEqual(len(assigned), 4)
                self.assertIn("city_norm", assigned)
                if row.method == "KMeans-weighted":
                    self.assertEqual(assigned.seed.unique().tolist(), [42])
                elif row.method == "MCLP":
                    checkpoint = (base / "out" / "checkpoints"
                                  / f"{row.scope}_MCLP_R{row.radius_km:g}_trajectory.npz")
                    with np.load(checkpoint, allow_pickle=False) as cached:
                        cumulative = cached["cumulative"]
                    self.assertAlmostEqual(row.search_runtime_s, cumulative[-1], places=12)
                    self.assertAlmostEqual(row.runtime_s, cumulative[int(row.K_selected) - 1], places=12)
                    if int(row.K_selected) == len(cumulative) and len(cumulative) > 1:
                        self.assertLess(row.search_runtime_s, prefix.runtime_s.sum())
            metadata = json.loads((base / "out" / "service_metadata.json").read_text())
            self.assertEqual(metadata["run_state"], "complete")
            self.assertEqual(metadata["required_orders"], 10)


if __name__ == "__main__":
    unittest.main()
