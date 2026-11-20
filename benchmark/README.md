# Benchmark

`expected_results.yaml` is the oracle for NIT section 5. **Never edit `inputs` or `nit_expected`.**
`test_oracle_integrity.py` guards them with a sha256 digest and re-derives every figure in the oracle with plain `Decimal` arithmetic.

| File | Purpose |
|---|---|
| `expected_results.yaml` | Inputs, NIT's expected results, AaharOS extended results, assumptions A1–A6 |
| `test_benchmark.py` | The 26 assertions (MASTER_PACK Part C), strict xfail until their MP lands |
| `test_oracle_integrity.py` | Oracle guard + consistency checks (pass from day one) |
| `runner.py` | Scoreboard; writes `results/latest.json` (read by the public guide page) |

Run: `make benchmark` (Docker) or, with the backend installed locally, `python benchmark/runner.py`.

When an MP turns an assertion green: replace `not_built(...)` with the real check (replay through the services,
compare with `oracle`), remove the `@pending` decorator, and confirm the scoreboard shows GREEN.
