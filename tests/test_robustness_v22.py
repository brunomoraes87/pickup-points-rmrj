"""Scientific invariants of the v22 sensitivity protocol (small reproducible cases)."""
from pathlib import Path
import math
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from shapely.geometry import box
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import robustness_v22 as r
from methods import method_mclp_heuristic

class RobustnessTests(unittest.TestCase):
    def test_finite_sample_coverage_inverse_quantiles(self):
        d = np.array([1., 3., 12.]); w = np.array([18, 1, 1])
        met = r.metrics_from_distances(d, w, 3)
        self.assertEqual(met["required_orders"], 19)
        self.assertEqual(met["covered_orders"], 19)
        self.assertTrue(met["feasible"])
        self.assertEqual(met["p95_km"], 3)
        self.assertEqual(met["p99_km"], 12)
        self.assertEqual(r.inverse_cdf(d, w, .95), np.quantile(np.repeat(d, w), .95, method="inverted_cdf"))
        self.assertFalse(r.metrics_from_distances(np.array([1., 4.]), np.array([19, 2]), 3)["feasible"])

    def test_all_seeds_same_integer_without_monotonicity(self):
        rows = []
        for k in (1, 2, 3, 4):
            for seed in r.SEEDS:
                feasible = (k == 4) or (k == 2 and seed in (42, 0)) or (k == 3 and seed in (1, 2, 3))
                rows.append(dict(K=k, seed=seed, feasible=feasible))
        self.assertEqual(r.first_feasible_integer(rows), 4)
        self.assertIsNone(r.first_feasible_integer(rows[:-1]))
        self.assertEqual(r.first_feasible_integer([dict(K=1, seed=0, feasible=True),
                                                    dict(K=2, seed=0, feasible=False)], seeds=(0,)), 1)

    def test_geodesic_evaluation_only_reuses_same_fitted_partition(self):
        df = pd.DataFrame(dict(CEP=["00001", "00002", "00003"],
                               lat=[-22., -22.03, -22.08],
                               lng=[-43., -43.05, -43.02], n_pedidos=[5, 2, 1]))
        co = r.Cohort("fixture", df, pd.DataFrame(), pd.DataFrame())
        a = r.Case("main", co, candidates=np.arange(3))
        b = r.Case("eval_only", co, metric="geodesic", fit_metric="haversine", candidates=np.arange(3))
        D = r.distances(df[["lat", "lng"]], df[["lat", "lng"]], "haversine")
        with tempfile.TemporaryDirectory() as folder:
            store = r.FitStore(folder, "fixture")
            for method, seed in (("Complete", -1), ("Average", -1), ("P-Median", -1),
                                 ("K-Means", 42), ("Ward", -1)):
                ra = r.fit_at_k(a, method, 2, seed, D, store)
                rb = r.fit_at_k(b, method, 2, seed, D, store)
                self.assertEqual(ra[-1], rb[-1])
                np.testing.assert_array_equal(ra[0], rb[0])
                np.testing.assert_array_equal(ra[1], rb[1])
        coords = np.array([[0., 0.], [1., 0.]])
        center = coords[:1]
        dh = r.distances(coords, center, "haversine").ravel()
        dg = r.distances(coords, center, "geodesic").ravel()
        w = np.array([18, 2])
        self.assertFalse(r.metrics_from_distances(dh, w, 110.8)["feasible"])
        self.assertTrue(r.metrics_from_distances(dg, w, 110.8)["feasible"])

    def test_full_record_dedup_keeps_same_coordinates_different_city(self):
        main = pd.DataFrame(dict(CEP=["00001"], lat=[0.], lng=[0.], n_pedidos=[1]))
        records = pd.DataFrame(dict(CEP=["00001"] * 4,
            geolocation_zip_code_prefix=["00001"] * 4, geolocation_lat=[0., 0., 0., 4.],
            geolocation_lng=[0.] * 4, geolocation_city=["a", "a", "b", "a"],
            geolocation_state=["RJ"] * 4, lat=[0., 0., 0., 4.], lng=[0.] * 4,
            source_row_number=[2, 3, 4, 5]))
        full = r.estimator_frame(main, records, "dedup_full")
        self.assertAlmostEqual(full.lat.iloc[0], 4 / 3)
        self.assertNotEqual(full.lat.iloc[0], 2.)  # coordinate-only dedup has a different estimand

    def test_greedy_trajectory_prefixes_equal_legacy_function(self):
        rng = np.random.default_rng(12)
        for n in (6, 13):
            df = pd.DataFrame(dict(lat=-22 + rng.normal(0, .025, n),
                                   lng=-43 + rng.normal(0, .025, n),
                                   n_pedidos=rng.integers(1, 6, n)))
            coords = df[["lat", "lng"]].to_numpy()
            candidates = np.arange(n)[::-1]
            D = r.distances(coords, coords)
            for radius in (1, 3, 10):
                seq, elapsed = r.greedy_trajectory(D[:, candidates], df.n_pedidos.to_numpy(float), radius)
                for k in range(1, n + 1):
                    labels, centers, _ = method_mclp_heuristic(df, k, radius, candidates)
                    opened = candidates[seq[:k]]
                    with self.subTest(n=n, radius=radius, K=k):
                        np.testing.assert_array_equal(centers, coords[opened])
                        np.testing.assert_array_equal(labels, D[:, opened].argmin(axis=1))
                self.assertTrue(np.all(np.diff(elapsed) >= 0))

    def test_projected_inverse_and_angular_mean_are_distinct(self):
        df = pd.DataFrame(dict(CEP=["00001", "00002", "00003"],
                               lat=[-22., -23.1, -22.4], lng=[-42., -44., -43.8],
                               n_pedidos=[10, 7, 4]))
        co = r.Cohort("fixture", df, pd.DataFrame(), pd.DataFrame())
        with tempfile.TemporaryDirectory() as folder:
            store = r.FitStore(folder, "test")
            a = r.Case("inverse", co, fit_space="projected", center_mode="inverse",
                       candidates=np.arange(3))
            b = r.Case("angular", co, fit_space="projected", center_mode="angular_mean",
                       candidates=np.arange(3))
            D = r.distances(df[["lat", "lng"]], df[["lat", "lng"]])
            for method, seed in (("K-Means", 42), ("Ward", -1)):
                ra = r.fit_at_k(a, method, 1, seed, D, store)
                rb = r.fit_at_k(b, method, 1, seed, D, store)
                np.testing.assert_array_equal(ra[0], rb[0])
                self.assertGreater(np.linalg.norm(ra[1] - rb[1]), 1e-5)
                x, y = r.FORWARD.transform(df.lng.to_numpy(), df.lat.to_numpy())
                w = df.n_pedidos.to_numpy(float)
                cx = np.average(x, weights=w); cy = np.average(y, weights=w)
                lng, lat = r.INVERSE.transform(cx, cy)
                np.testing.assert_allclose(ra[1][0], [lat, lng], atol=1e-12)

    def test_hypothetical_orders_preserve_main_coordinates_and_declared_city(self):
        main = pd.DataFrame(dict(CEP=["00001"], lat=[1.], lng=[2.], n_pedidos=[2], city_norm=["original"]))
        cols = ["order_id", "customer_id", "customer_unique_id", "CEP", "city_norm",
                "municipio_original", "municipality_for_sensitivity", "municipality_origin"]
        orders = pd.DataFrame([["o1", "c1", "u1", "00001", "original", "Original", "original", "cadastro_principal"],
                               ["o2", "c2", "u2", "00001", "original", "Original", "original", "cadastro_principal"]],
                              columns=cols)
        extra = pd.DataFrame(dict(order_id=["o3", "o4"], customer_id=["c3", "c4"],
                                 customer_unique_id=["u3", "u4"], CEP=["00001", "00002"],
                                 municipio_original=["papucaia", "tocos"],
                                 municipio_inferido=["cachoeiras de macacu", "rio de janeiro"],
                                 lat=[9., 5.], lng=[8., 6.]))
        co = r.add_hypothetical_orders(main, orders, pd.DataFrame(), extra, "Dfixture")
        self.assertEqual(co.df.n_pedidos.sum(), 4)
        self.assertEqual(co.df.set_index("CEP").loc["00001", "lat"], 1.)
        self.assertEqual(co.df.set_index("CEP").loc["00002", "lat"], 5.)
        self.assertEqual(co.orders.loc[co.orders.order_id.eq("o3"), "municipio_original"].iloc[0], "papucaia")
        self.assertEqual(co.orders.loc[co.orders.order_id.eq("o3"), "municipality_origin"].iloc[0], "inferencia_prefixo_omisso")

    def test_municipal_counts_and_zero_coverage_conserved(self):
        df = pd.DataFrame(dict(CEP=["00001", "00002"], n_pedidos=[2, 1]))
        orders = pd.DataFrame(dict(order_id=["a", "b", "c"], CEP=["00001", "00001", "00002"],
                                  municipality_for_sensitivity=["rio de janeiro", "a", "a"],
                                  municipality_origin=["cadastro_principal"] * 3))
        frame, met = r.municipal_metrics(orders, df, np.array([1., 9.]), 3,
                                        ["rio de janeiro", "a", "no_orders"])
        self.assertEqual(frame.N_orders.sum(), 3)
        self.assertEqual(frame.covered_orders.sum(), 2)
        self.assertEqual(met["municipalities_zero"], 0)
        self.assertEqual(met["municipalities_below80"], 1)
        self.assertEqual(met["orders_in_below80_municipalities"], 2)
        self.assertEqual(met["rio_share_of_uncovered_pct"], 0.)

    def test_fractional_redistribution_does_not_multiply_orders(self):
        df = pd.DataFrame(dict(CEP=["00001", "00002"], n_pedidos=[3, 2]))
        records = pd.DataFrame(dict(CEP=["00001"] * 2 + ["00002"] * 3,
                                    lat=[0.] * 5, lng=[0., 0., 1., 1., 1.]))
        met = r.redistribution_metrics(records, df, np.array([[0., 0.]]), 3)
        self.assertAlmostEqual(met["redistributed_N_fractional"], 5.)
        self.assertAlmostEqual(met["redistributed_covered_fractional"], 3.)
        self.assertAlmostEqual(met["redistributed_coverage_pct"], 60.)

    def test_missing_or_infeasible_variants_not_classified(self):
        rows = [dict(case=case, method=method, radius_km=radius,
                     status="selected", K_selected=10 if method == "A" else 20)
                for case in ("main", "median") for method in ("A", "B") for radius in r.RADII]
        frame = pd.DataFrame(rows)
        complete = r.conservative_comparison(frame, ("main", "median"), ("A", "B"))
        self.assertTrue(complete.classification.eq("stable_observed_order").all())
        missing = r.conservative_comparison(frame, ("main", "median", "dedup"), ("A", "B"))
        self.assertTrue(missing.classification.eq("incomplete_variants_no_classification").all())
        frame.loc[(frame.case == "median") & (frame.method == "A"), "K_selected"] = 20
        overlap = r.conservative_comparison(frame, ("main", "median"), ("A", "B"))
        self.assertTrue(overlap.classification.eq("absence_of_robust_descriptive_separation").all())
        frame.loc[(frame.case == "median") & (frame.method == "A"), "status"] = "structurally_infeasible"
        self.assertTrue(r.conservative_comparison(frame, ("main", "median"), ("A", "B"))
                        .classification.eq("incomplete_variants_no_classification").all())

    def test_atomic_lock_retry_bounded_and_unrelated_errors_not_masked(self):
        with patch.object(r.os, "replace", side_effect=[PermissionError("lock"), PermissionError("lock"), None]) as replace:
            with patch.object(r.time, "sleep") as sleep:
                r.replace_retry("source", "target")
            self.assertEqual(replace.call_count, 3)
            self.assertEqual([x.args[0] for x in sleep.call_args_list], [.05, .1])
        with patch.object(r.os, "replace", side_effect=PermissionError("permanent")) as replace:
            with patch.object(r.time, "sleep"):
                with self.assertRaises(PermissionError):
                    r.replace_retry("source", "target")
            self.assertEqual(replace.call_count, 6)
        with patch.object(r.os, "replace", side_effect=FileNotFoundError("missing")) as replace:
            with self.assertRaises(FileNotFoundError):
                r.replace_retry("source", "target")
            self.assertEqual(replace.call_count, 1)

    def test_small_fresh_full_search_exports_first_feasible_and_conserves_orders(self):
        df = pd.DataFrame(dict(CEP=["00001", "00002", "00003"],
                               lat=[-22.] * 3, lng=[-43., -43.03, -43.1], n_pedidos=[5, 2, 1]))
        orders = pd.DataFrame(dict(order_id=[f"o{i}" for i in range(8)],
                                  customer_unique_id=[f"u{i}" for i in range(8)],
                                  CEP=["00001"] * 5 + ["00002"] * 2 + ["00003"],
                                  municipality_for_sensitivity=["rio de janeiro"] * 8,
                                  municipality_origin=["cadastro_principal"] * 8))
        records = df[["CEP", "lat", "lng"]].copy()
        co = r.Cohort("fixture", df, orders, records)
        case = r.Case("fixture", co, candidates=np.array([0, 1, 2]))
        union = box(-44., -23., -42., -21.)
        with tempfile.TemporaryDirectory() as folder:
            runner = r.SearchRunner(folder, "fixture", union, {"rio de janeiro": union})
            runner.run_case(case)
            selection = pd.DataFrame(runner.selection)
            self.assertEqual(len(selection), 18)
            self.assertTrue(selection.status.eq("selected").all())
            curves = pd.DataFrame(runner.curves)
            for row in selection.itertuples():
                curve = curves[(curves.method == row.method) & (curves.radius_km == row.radius_km)]
                seeds = r.SEEDS if row.method == "K-Means" else (-1,)
                self.assertEqual(r.first_feasible_integer(curve.to_dict("records"), seeds),
                                 row.K_selected)
                prior = curve[curve.K < row.K_selected]
                self.assertEqual(set(prior.K), set(range(1, row.K_selected)))
                self.assertGreaterEqual(row.covered_orders, math.ceil(.95 * 8))
            self.assertEqual(pd.DataFrame(runner.municipal).N_orders.sum(), 18 * 8)
            self.assertEqual(pd.DataFrame(runner.network_summary).redistributed_N_fractional.sum(), 18 * 8)
            self.assertEqual(len(list((Path(folder) / "networks").glob("*_assignments.csv"))), 18)

    def test_administrative_segment_flags_do_not_claim_water(self):
        df = pd.DataFrame(dict(CEP=["00001", "00002"], lat=[-22., -22.],
                               lng=[-43., -43.], n_pedidos=[2, 1]))
        centers = np.array([[-22., -43.], [-22., -43.02]])
        facility, segments, met = r.geometry_flags(df, centers, np.array([0, 1]),
                                                   box(-43.01, -22.01, -42.99, -21.99))
        self.assertEqual(met["outside_union_facilities"], 1)
        self.assertEqual(met["orders_nearest_to_outside_facilities"], 1)
        self.assertGreater(segments.external_union_segment_km_projected.iloc[1], 0)
        self.assertIn("not a water crossing", met["geometry_interpretation"])

if __name__ == "__main__":
    unittest.main()
