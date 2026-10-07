"""Reduced independent checks: known distances, counts, municipality conservation,
nearest/load corruption, administrative boundary and MILP versus enumeration."""
import ast
import importlib.util
import itertools
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

PATH=Path(__file__).resolve().parents[1]/"scripts/10_verify_v22_independent.py"
spec=importlib.util.spec_from_file_location("standalone_verifier",PATH)
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class IndependentVerificationTests(unittest.TestCase):
    def test_known_haversine_distances_and_symmetry(self):
        points=np.array([[0,0],[0,90],[0,180],[90,0]],float)
        D=v.distance_matrix(points,points)
        np.testing.assert_allclose(D,D.T,atol=1e-9)
        np.testing.assert_allclose(np.diag(D),0,atol=1e-9)
        self.assertAlmostEqual(D[0,1],np.pi*v.EARTH_KM/2,places=8)
        self.assertAlmostEqual(D[0,2],np.pi*v.EARTH_KM,places=8)
        self.assertAlmostEqual(D[0,3],np.pi*v.EARTH_KM/2,places=8)

    def test_wgs84_one_degree_equator(self):
        D=v.distance_matrix([[0,0]],[[0,1]],"geodesic")
        self.assertAlmostEqual(D[0,0],111.31949079327357,places=8)
        self.assertGreater(D[0,0],v.distance_matrix([[0,0]],[[0,1]])[0,0])

    def test_weighted_empirical_rank_and_coverage(self):
        m=v.recalculate_metrics([1,2,100],[19,1,1],2)
        self.assertEqual(m["required_orders"],20)
        self.assertEqual(m["covered_orders"],20)
        self.assertEqual(m["p95_empirical_km"],2)
        self.assertEqual(m["median_empirical_km"],1)
        self.assertEqual(m["p99_empirical_km"],100)
        self.assertTrue(m["target_met"])
        self.assertEqual(v.recalculate_metrics([1,2,100],[19,1,1],1)["target_met"],False)
        self.assertEqual(v.recalculate_metrics([0],[9691],0)["required_orders"],9207)
        with self.assertRaises(ValueError):v.recalculate_metrics([0],[.5],1)

    def fixture(self):
        demand=pd.DataFrame({"CEP":["00001","00002"],"lat":[0.,0.],"lng":[0.,1.],"n_pedidos":[2,1]})
        orders=pd.DataFrame({"order_id":["a","b","c"],"CEP":["00001","00001","00002"],"city_norm":["alpha","beta","beta"]})
        return demand,orders

    def test_per_order_city_preserves_mixed_prefix(self):
        demand,orders=self.fixture()
        p=v.municipal_profile(orders,demand,np.array([1.,10.]),3,names=["alpha","beta","gamma"]).set_index("city")
        self.assertEqual(p.total_orders.sum(),3)
        self.assertEqual(p.loc["alpha","covered_orders"],1)
        self.assertEqual(p.loc["beta","total_orders"],2)
        self.assertEqual(p.loc["beta","covered_orders"],1)
        self.assertEqual(p.loc["gamma","total_orders"],0)

    def test_rejects_lost_or_duplicated_orders(self):
        demand,orders=self.fixture()
        with self.assertRaises(ValueError):v.municipal_profile(orders.iloc[:2],demand,[0,0],1)
        with self.assertRaises(ValueError):v.municipal_profile(pd.concat([orders,orders.iloc[:1]]),demand,[0,0],1)

    def test_fractional_redistribution_conserves_orders_without_multiplication(self):
        demand,orders=self.fixture()
        records=pd.DataFrame({"CEP":["00001","00001","00002"],
            "geolocation_lat":[0.,0.,0.],"geolocation_lng":[0.,.01,.1]})
        met=v.fractional_redistribution(records,demand,[[0,0]],1.2)
        self.assertEqual(met["redistributed_N_fractional"],3)
        self.assertEqual(met["redistributed_covered_fractional"],2)
        self.assertAlmostEqual(met["redistributed_coverage_pct"],200/3)
        with self.assertRaises(ValueError):v.fractional_redistribution(records.iloc[:2],demand,[[0,0]],1.2)

    def test_administrative_boundary_and_hole(self):
        auditor=v.Auditor(SimpleNamespace())
        auditor.union=Polygon([(0,0),(2,0),(2,2),(0,2)],holes=[[(.5,.5),(1.5,.5),(1.5,1.5),(.5,1.5)]])
        np.testing.assert_array_equal(auditor.inside([[0,1],[1,1],[3,1],[.5,1]]),[True,False,False,True])

    def test_legacy_candidate_regime_keeps_all_and_prefix_order(self):
        demand=pd.DataFrame({"CEP":["00003","00001","00002"],"lat":[0.,0.,3.],"lng":[0.,0.,0.],"n_pedidos":[10,1,5]})
        union=Polygon([(-1,-1),(1,-1),(1,1),(-1,1)])
        np.testing.assert_array_equal(v.postal_candidate_positions(demand,"J_all828_legacy_order",union),[1,2,0])
        np.testing.assert_array_equal(v.postal_candidate_positions(demand,"J_union825_legacy_order",union),[1,0])
        self.assertEqual(len(demand),3)

    def test_integer_comparison_has_no_relative_tolerance(self):
        auditor=v.Auditor(SimpleNamespace())
        auditor.compare(10**10+1,10**10,"integer",0)
        self.assertEqual(len(auditor.failures),1)

    def test_canonical_input_keys_resolve_locations_without_changing_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"olist_geolocation_dataset.csv"
            source.write_text("coordinate\n",encoding="utf-8")
            key="raw/olist_geolocation_dataset.csv";digest=v.sha(source)
            for field in ("input_locations","input_paths"):
                actual,expected=v.resolve_input_location({"input_hashes":{key:digest},field:{key:str(source)}},source.name)
                self.assertEqual(actual,source);self.assertEqual(expected,digest)
            actual,expected=v.resolve_input_location({"input_hashes":{str(source):digest}},source.name)
            self.assertEqual(actual,source);self.assertEqual(expected,digest)
            with self.assertRaises(ValueError):v.resolve_input_location({"input_hashes":{key:digest}},source.name)

    def test_final_manifest_requires_explicit_preserved_provenance(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            native={"output_hashes":{"result.csv":"native"}}
            self.assertEqual(v.select_output_manifest(native,root),(native["output_hashes"],None))
            consolidated={"output_hashes":{"result.csv":"old"},"raw_output_hashes":{"result.csv":"final"},
                          "initial_execution_signature":"initial"}
            with self.assertRaises(ValueError):v.select_output_manifest(consolidated,root)
            initial=root/"metadata_initial_execution.json"
            initial.write_text(json.dumps({"signature_sha256":"initial","output_hashes":consolidated["output_hashes"]}),encoding="utf-8")
            self.assertEqual(v.select_output_manifest(consolidated,root),(consolidated["raw_output_hashes"],initial))
            initial.write_text(json.dumps({"signature_sha256":"other","output_hashes":consolidated["output_hashes"]}),encoding="utf-8")
            with self.assertRaises(ValueError):v.select_output_manifest(consolidated,root)

    def test_detects_corrupted_facility_load(self):
        demand,orders=self.fixture()
        auditor=v.Auditor(SimpleNamespace())
        auditor.names=["alpha","beta"]
        auditor.union=Polygon([(-2,-2),(2,-2),(2,2),(-2,2)])
        facilities=pd.DataFrame({"facility_id":[0,1],"lat":[0.,0.],"lng":[0.,1.],"nearest_assigned_orders":[1,2]})
        assignment=demand.assign(nearest_facility=[0,1],distance_km=[0.,0.],outside_R=[False,False])
        row=dict(K_selected=2,radius_km=3,**v.recalculate_metrics([0,0],[2,1],3))
        auditor.network("fixture",row,demand,orders,facilities,assignment)
        self.assertEqual([x["check"] for x in auditor.failures],["fixture: exported loads"])

    def test_independent_milp_matches_finite_enumeration(self):
        coords=np.array([[0,0],[0,.01],[0,.02],[0,.03],[0,.1]],float)
        w=np.array([2,3,5,1,1]);R=1.2
        D=v.distance_matrix(coords,coords)
        minimum=None
        for K in range(1,6):
            for selected in itertools.combinations(range(5),K):
                covered=int(w[(D[:,selected]<=R).any(axis=1)].sum())
                if covered>=12:minimum=K;break
            if minimum is not None:break
        result=v.independent_cover_benchmark(coords,w,np.arange(5),R,time_limit=10)
        self.assertEqual(result["status"],0)
        self.assertEqual(result["K"],minimum)
        self.assertTrue(result["primal_verified"])
        self.assertAlmostEqual(result["primal_objective"],result["dual_bound"],places=8)

    def test_three_map_extremes_accept_integer_radius_and_detect_bad_point(self):
        with tempfile.TemporaryDirectory() as folder:
            auditor=v.Auditor(SimpleNamespace(main_dir=Path(folder)))
            df=pd.DataFrame({"CEP":["00001","00002","00003","00004"],"lat":[0.]*4,
                             "lng":[.01,.02,.03,.04],"n_pedidos":[1,2,3,4]})
            fac=pd.DataFrame({"facility_id":[0],"lat":[0.],"lng":[0.]})
            d=v.distance_matrix(df[["lat","lng"]],fac[["lat","lng"]]).ravel()
            auditor.cache["main:main:fixture:3.0"]=dict(demand=df,facilities=fac,distances=d,
                reported_nearest=np.zeros(4,int))
            rows=[dict(scope="main",method="fixture",radius_km=3,K=1,CEP=df.CEP.iloc[i],
                orders=int(df.n_pedidos.iloc[i]),distance_km=d[i],facility_id=0,lat=0.,
                lng=df.lng.iloc[i],facility_lat=0.,facility_lng=0.) for i in (3,2,1)]
            path=Path(folder)/"figure_map_extremes_v22.csv"
            pd.DataFrame(rows).to_csv(path,index=False)
            auditor.validate_figures()
            self.assertEqual(auditor.failures,[])
            rows[0]["lat"]=1.
            pd.DataFrame(rows).to_csv(path,index=False)
            auditor.validate_figures()
            self.assertTrue(any("latitude" in x["check"] for x in auditor.failures))

    def test_standalone_verifier_has_no_repository_import(self):
        tree=ast.parse(PATH.read_text(encoding="utf-8"))
        imported=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imported.extend(x.name for x in node.names)
            if isinstance(node,ast.ImportFrom):imported.append(node.module or "")
        forbidden=("methods","candidate_sets","exact_benchmarks","robustness_v22","scripts")
        self.assertFalse(any(x.split(".")[0] in forbidden for x in imported))


if __name__=="__main__":
    unittest.main()
