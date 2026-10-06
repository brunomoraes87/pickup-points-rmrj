"""Analytical checks of weighting, coverage and native/nearest assignments."""
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from methods import EARTH_R_KM,evaluate
def demand(distances,orders):
    return pd.DataFrame({"lat":np.zeros(len(distances)),"lng":np.asarray(distances)*180/(np.pi*EARTH_R_KM),"n_pedidos":orders})
def centers(distances):
    return np.column_stack([np.zeros(len(distances)),np.asarray(distances)*180/(np.pi*EARTH_R_KM)])
class MetricTests(unittest.TestCase):
    def test_order_weighted_and_unweighted_percentiles(self):
        r=evaluate(demand([0,1,2,10],[97,1,1,1]),np.zeros(4,dtype=int),centers([0]))
        for key,value in {"median_distance_km":0,"p95_distance_km":0,"p99_distance_km":2.08,
                          "p95_CEPs_distance_km":8.8,"p99_CEPs_distance_km":9.76,"weighted_avg_distance_km":.13}.items():
            self.assertAlmostEqual(r[key],value,places=6)
    def test_nearest_assignment_does_not_follow_incorrect_native_labels(self):
        r=evaluate(demand([0,1,9],[2,3,5]),np.array([1,1,0]),centers([0,10]))
        self.assertAlmostEqual(r["weighted_avg_distance_km"],.8)
        self.assertAlmostEqual(r["max_distance_km"],1)
        self.assertAlmostEqual(r["native_max_distance_km"],10)
        self.assertEqual(r["CEPs_reassigned_to_nearest"],3)
        self.assertEqual(r["orders_reassigned_to_nearest"],10)
    def test_native_noise_and_operational_coverage_are_different(self):
        r=evaluate(demand([0,1,9],[2,3,5]),np.array([1,-1,0]),centers([0,10]))
        self.assertEqual(r["assigned_orders_pct"],100)
        self.assertEqual(r["native_assigned_orders_pct"],70)
        self.assertEqual(r["orders_reassigned_to_nearest"],7)
    def test_weights_must_be_positive_integer_counts(self):
        for orders in ([1,0],[1,-1],[1,1.5]):
            with self.subTest(orders=orders),self.assertRaises(ValueError):
                evaluate(demand([0,1],orders),np.zeros(2,dtype=int),centers([0]))
    def test_no_facilities_give_zero_coverage_and_assignment(self):
        r=evaluate(demand([0,1],[2,3]),np.array([-1,-1]),np.empty((0,2)))
        self.assertEqual(r["assigned_orders_pct"],0)
        self.assertEqual(r["coverage_3km_%"],0)
        self.assertTrue(np.isnan(r["p99_distance_km"]))
if __name__=="__main__":unittest.main()
