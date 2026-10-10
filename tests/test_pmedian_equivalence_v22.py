"""Scientific regression: optimized interchange must preserve the v21 trajectory."""
import sys,unittest
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from methods import method_pmedian_heuristic,haversine_pairwise

def frozen_v21(df,p,candidates,max_iter):
    xy=df[['lat','lng']].to_numpy();w=df.n_pedidos.to_numpy(float)
    d=haversine_pairwise(xy[:,0],xy[:,1])[:,candidates]
    def objective(s):return float(np.sum(w*d[:,s].min(axis=1)))
    selected=[];available=list(range(len(candidates)))
    for _ in range(p):
        best=None;value=np.inf
        for j in available:
            trial=objective(selected+[j])
            if trial<value:value=trial;best=j
        selected.append(best);available.remove(best)
    improved=True;passes=0
    while improved and passes<max_iter:
        improved=False;passes+=1
        for k,jin in enumerate(list(selected)):
            value=objective(selected)
            for jout in available:
                trial=selected.copy();trial[k]=jout;cost=objective(trial)
                if cost<value-1e-9:
                    selected=trial;available.remove(jout);available.append(jin)
                    value=cost;improved=True;break
    return d[:,selected].argmin(axis=1),xy[np.asarray(candidates)[selected]],passes,not improved

class PmedianEquivalenceTests(unittest.TestCase):
    def test_legacy_labels_centers_passes_and_termination_under_ties_and_limits(self):
        rng=np.random.default_rng(92117)
        for trial in range(10):
            n=5+trial;xy=rng.normal(size=(n,2))*.12+[-23,-43]
            if trial%3==0:xy[-1]=xy[0]
            df=pd.DataFrame({'lat':xy[:,0],'lng':xy[:,1],'n_pedidos':rng.integers(1,20,n)})
            candidates=rng.permutation(n)[:max(3,n-2)]
            for p in sorted({1,2,min(5,len(candidates)),len(candidates)}):
                for limit in [1,3,100]:
                    with self.subTest(trial=trial,p=p,limit=limit):
                        old=frozen_v21(df,p,candidates,limit)
                        new=method_pmedian_heuristic(df,p,candidates,limit,return_diagnostics=True)
                        np.testing.assert_array_equal(old[0],new[0]);np.testing.assert_array_equal(old[1],new[1])
                        self.assertEqual(old[2],new[3]['pmedian_passes']);self.assertEqual(old[3],new[3]['pmedian_converged'])
    def test_precomputed_distance_uses_declared_metric(self):
        df=pd.DataFrame({'lat':[-23,-23.01,-23.02],'lng':[-43]*3,'n_pedidos':[1,2,3]})
        alternate=np.array([[0,100,1],[100,0,2],[1,2,0]],float)
        _,centers,_,diag=method_pmedian_heuristic(df,1,distance_matrix=alternate,return_diagnostics=True)
        np.testing.assert_array_equal(centers,df[['lat','lng']].to_numpy()[[2]])
        self.assertEqual(diag['pmedian_objective_weighted_km'],5)
    def test_invalid_candidate_budget_is_explicit(self):
        df=pd.DataFrame({'lat':[-23,-23.01],'lng':[-43]*2,'n_pedidos':[1,2]})
        for p,candidates in [(0,[0]),(2,[0]),(1,[0,0]),(1,[-1])]:
            with self.subTest(p=p,candidates=candidates),self.assertRaises(ValueError):
                method_pmedian_heuristic(df,p,candidates)

if __name__=='__main__':unittest.main()
