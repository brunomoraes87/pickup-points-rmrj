"""Synthetic boundary, source identity and data-conservation checks."""
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from data_quality import validate_geolocation, audit_aggregated_coordinates, PREFIX, LAT, LNG

GEO = {"type":"FeatureCollection", "features":[{"type":"Feature",
       "properties":{"codarea":"3303302"}, "geometry":{"type":"Polygon",
       "coordinates":[[[-44,-24],[-42,-24],[-42,-22],[-44,-22],[-44,-24]],
                      [[-43.2,-23.2],[-43.2,-22.8],[-42.8,-22.8],[-42.8,-23.2],[-43.2,-23.2]]]}}]}
def row(prefix=24027, lat=-23, lng=-43.5, state="RJ"):
    return {PREFIX:prefix,LAT:lat,LNG:lng,"geolocation_city":"niteroi","geolocation_state":state}
def review(number, record, decision="exclude_outside_region"):
    return {**record,"source_row_number":number,"decision":decision,"reason":"Documented synthetic review"}
class GeographyTests(unittest.TestCase):
    def validate(self, records, requested=(24027,), reviews=None):
        return validate_geolocation(pd.DataFrame(records), requested, GEO, ["3303302"], reviews)
    def test_inside_wrong_text_outer_and_hole_boundaries_retained(self):
        clean,audit,summary=self.validate([row(state="GO"),row(lng=-44),row(lng=-43.2)])
        self.assertEqual(len(clean),3)
        self.assertEqual(audit.status.tolist(),["inside_region"]*3)
    def test_hole_far_and_near_outside_all_require_explicit_review(self):
        for lng in (-43,-45,-44.000001):
            with self.subTest(lng=lng), self.assertRaisesRegex(ValueError,"Missing reviewed"):
                self.validate([row(lng=lng)])
    def test_decisions_retain_boundary_and_remove_confirmed_outside(self):
        far,near=row(lng=-45),row(lng=-44.000001)
        clean,audit,summary=self.validate([far,near],reviews=pd.DataFrame([
            review(2,far),review(3,near,"retain_boundary_uncertainty")]))
        self.assertEqual(clean.source_row_number.tolist(),[3])
        self.assertEqual(summary["excluded_rows"],1)
        self.assertEqual(summary["retained_boundary_uncertainty_rows"],1)
    def test_review_exact_source_identity_required(self):
        source=row(lng=-45)
        for field,val in [(PREFIX,24028),(LAT,np.nextafter(-23.,-np.inf)),(LNG,np.nextafter(-45.,-np.inf))]:
            r=review(2,source);r[field]=val
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"Source mismatch"):
                self.validate([source],reviews=pd.DataFrame([r]))
    def test_invalid_rows_do_not_discard_valid_same_prefix(self):
        clean,audit,summary=self.validate([row(lat="bad"),row(lat=np.nan),row(lat=np.inf),row(lat=91),row(lng=181),row()])
        self.assertEqual(len(clean),1)
        self.assertEqual(summary["invalid_coordinate_rows"],5)
        self.assertEqual(clean.source_row_number.tolist(),[7])
    def test_original_row_number_input_and_repetitions_preserved(self):
        original=pd.DataFrame([row(prefix=99999),row(),row()],index=[90,80,70])
        before=original.copy(deep=True)
        clean,audit,summary=validate_geolocation(original,[24027,24325],GEO,["3303302"])
        pd.testing.assert_frame_equal(original,before)
        self.assertEqual(clean.source_row_number.tolist(),[3,4])
        self.assertEqual(summary["duplicate_geo_rows_after_first_retained"],1)
        self.assertEqual(summary["prefixes_without_retained_coordinates"],["24325"])
    def test_duplicate_and_extra_review_rejected(self):
        source=row(lng=-45);r=review(2,source)
        with self.assertRaisesRegex(ValueError,"Duplicate review"):
            self.validate([source],reviews=pd.DataFrame([r,r]))
        with self.assertRaisesRegex(ValueError,"do not correspond"):
            self.validate([row()],reviews=pd.DataFrame([review(2,row())]))
    def test_missing_geometry_and_empty_target(self):
        with self.assertRaisesRegex(ValueError,"missing from GeoJSON"):
            validate_geolocation(pd.DataFrame([row()]),[24027],GEO,["0000000"])
        clean,audit,summary=self.validate([row(prefix=99999)])
        self.assertTrue(clean.empty and audit.empty)
        self.assertEqual(summary["prefixes_without_retained_coordinates"],["24027"])
    def test_derived_mean_in_hole_is_flagged_without_demand_removal(self):
        source=pd.DataFrame({"lat":[-23.],"lng":[-43.],"n_pedidos":[35]})
        before=source.copy(deep=True)
        audited=audit_aggregated_coordinates(source,GEO,["3303302"])
        self.assertFalse(audited.iloc[0].mean_inside_region)
        self.assertEqual(audited.n_pedidos.sum(),35)
        pd.testing.assert_frame_equal(source,before)
if __name__=="__main__":unittest.main()
