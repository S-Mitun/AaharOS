# ADR-0000: Which source wins when documents disagree

- Status: Accepted (MP00, 2026-11-21)

## Context
The project has five planning sources: the NIT brief, the benchmark oracle, `CLAUDE.md`, `docs/MASTER_PACK.md` (v2)
and an earlier pack kept at `docs/reference/MASTER_PACK_v1.md`. They overlap and sometimes disagree.

## Decision
Precedence, highest first:

1. `docs/PROBLEM_STATEMENT.md` (the NIT brief)
2. `benchmark/expected_results.yaml`: `inputs` and `nit_expected` (sacred, sha256-guarded)
3. `CLAUDE.md`
4. `docs/MASTER_PACK.md` (v2)
5. `docs/reference/MASTER_PACK_v1.md` (reference only)

## Conflicts found between v1 and v2 (all resolved in favour of v2 + CLAUDE.md)

| Topic | v1 | v2 / CLAUDE.md (followed) |
|---|---|---|
| MP numbering | MP01 = UX, MP02 = domain model | MP01 = domain model + ERD, UX spread across MP06–MP15 |
| Backend layout | layered `api/ services/ models/` | per-module `modules/<m>/{api,service,domain,models,schemas}.py` |
| Auditor role name | `ACCOUNTANT_AUDITOR` | `AUDITOR` |
| Pouch variance | only batch view (−3%) | both views; flexible standard (+3.19%, flagged) is primary |
| Double entry | "full double-entry accounting is out of scope" | double-entry **stock** ledger (qty + value), not a general ledger. Compatible. |
| Scripts | `scripts/run_benchmark.py` etc. | `make` targets (`make benchmark`, `make seed-benchmark`) |

## Consequences
When a later MP finds a new conflict it adds a row here instead of picking silently.
