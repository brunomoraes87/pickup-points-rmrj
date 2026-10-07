# Verificação independente v22

Estado: **PASSED**. Redes recalculadas: 221. Verificações: 60232.

Falhas: 0; pendências: 0.

Os cálculos foram reimplementados sem importar módulos do repositório. Cobertura usa d ≤ R e os percentis empíricos usam o posto inteiro ceil(q×N).

Tolerâncias: distâncias 1e-07 km absolutos; coordenadas 1e-10 graus; percentuais 1e-07 pontos; contagens inteiras sem tolerância.

## Benchmark independente

{
  "solver": "SciPy milp/HiGHS",
  "independent_second_solver": false,
  "status": 0,
  "message": "Optimization terminated successfully. (HiGHS Status 7: Optimal)",
  "runtime_s": 0.8551827999763191,
  "primal_objective": 35.0,
  "dual_bound": 35.0,
  "gap": 0.0,
  "K": 35,
  "covered_orders": 9228,
  "required_orders": 9207,
  "candidate_ceiling_orders": 9344,
  "selected_postal_positions": [
    267,
    292,
    252,
    401,
    824,
    76,
    265,
    116,
    442,
    633,
    638,
    84,
    324,
    362,
    233,
    658,
    511,
    542,
    594,
    614,
    672,
    698,
    203,
    461,
    577,
    708,
    419,
    758,
    149,
    161,
    310,
    297,
    373,
    493,
    494
  ],
  "primal_verified": true,
  "limitation": "Independent model assembly and code, same installed SciPy/HiGHS solver; no cross-solver confirmation",
  "alternative_solver_inventory": {
    "modules": {
      "pulp": false,
      "ortools": false,
      "mip": false,
      "cvxpy": false,
      "highspy": false
    },
    "external_commands": {
      "cbc": null,
      "glpsol": null,
      "scip": null
    }
  }
}

O modelo foi montado de forma independente, mas usa o mesmo SciPy/HiGHS disponível. Isso confirma a implementação e não constitui validação por um segundo solver.

## Limitações

- No repository modules imported; source artifacts are inputs, not instructions.
- Administrative union only: flags do not certify dry land, water crossings, road access or commercial eligibility.
- Does not independently refit every cluster search K; exported curves support enumeration checks.
- Same installed SciPy/HiGHS solver for independently assembled benchmark; not a second solver.
- No proof that centroid distances equal individual-address distances or operational routes.
- Raw-geolocation reconstruction checks estimator outputs, not factual address correctness.

Hashes dos arquivos lidos, métricas por rede, evidências e ambiente estão registrados no JSON. Nenhum input foi alterado.
