# Invariants

Rules that must hold after every committed transaction. Each one says **where it is enforced** (the strongest place
first) and **which test proves it**. Layers: **DB** = constraint or trigger in PostgreSQL (MP02), **SVC** = service
code in one transaction, **CLI** = `make integrity`, **TEST** = automated test. Test ids are the names the owning MP
must use.

## The four conservation laws

| # | Law | Statement | Enforced | Test |
|---|---|---|---|---|
| L1 | **Quantity** | For every stock journal and every item, Σ `qty_base` = 0. | DB: deferred constraint trigger on `stock_lines` · SVC: `ledger.domain.build_journal` rejects before insert · CLI: re-sums all journals | `db:test_unbalanced_journal_rejected` (MP02), `ledger:test_state_machine` (MP04, ≥ 500 examples), `bench:a26` |
| L2 | **Value** | For every journal, Σ `value` = 0 across its lines. Per run: value into FG (on hand + dispatched) = materials consumed + conversion costs. Variances are explicit `variance_results` rows that sum exactly to actual − standard; nothing is left as silent residue. | DB: same deferred trigger checks Σ value · SVC: costing true-up computes the last line as the remainder · CLI: per-run check | `costing:test_lot_value_equals_run_cost`, `costing:test_waterfall_sums_exactly`, `bench:a19`, `bench:a22` |
| L3 | **Mass** | Per run: expected bulk = good packed mass + recorded scrap + recorded loss + **unexplained gap**. The gap is computed and shown, never hidden or forced to zero. | SVC: `production.domain.mass_balance` · UI: mass-balance card | `production:test_mass_balance_gap_shown` (40.0 = 37.6 + 0 + 0 + 2.4) |
| L4 | **Tax** | Σ invoice tax lines = GST summary report = GSTR-shaped export, for any period. | SVC: reports read `invoice_tax_lines` only · CLI: three-way tie-out | `tax:test_sum_lines_equals_header` (property), `reports:test_gst_tieout`, `bench:a26` |

## Stock

| # | Invariant | Enforced | Test |
|---|---|---|---|
| S1 | Store balances never go negative: for every STORE location × item × lot, qty ≥ 0. Virtual locations may go negative. | DB: CHECK on `inventory_balances` for STORE rows (projection updated in the same transaction) · SVC: `SELECT … FOR UPDATE` before posting | `ledger:test_negative_stock_rejected`, `ledger:test_state_machine` |
| S2 | Available to promise = on hand − reserved ≥ 0 for each FG item at FG_STORE. Approval reserves; never over-reserves. | SVC: reservation inside the approval transaction with the balance row locked | `sales:test_race_last_packets` (two parallel approvals, exactly one wins), `bench:a13` |
| S3 | Balances are a projection: rebuilding `inventory_balances` from `stock_lines` gives identical rows. No endpoint writes a balance. | DB: `inventory_balances` writable only by the ledger role (MP02 grants) · CLI: rebuild + diff | `ledger:test_projection_equals_rebuild`, `bench:a26` |
| S4 | Every journal has a source: `source_type` and `source_id` are NOT NULL and point to a posted document. | DB: NOT NULL + CHECK on allowed types · SVC: posting API requires a source | `ledger:test_journal_without_source_rejected` |
| S5 | A dispatch never exceeds what was reserved for that order line, and only picks non-expired lots (FEFO). | SVC: dispatch service checks reservation and best_before | `dispatch:test_dispatch_over_reserved_rejected`, `dispatch:test_expired_lot_not_picked`, `bench:a21` |
| S6 | WIP for a completed run is zero: what was issued to WIP was either consumed by the completion journal or returned. | SVC: completion consumes the run's net issues · CLI | `production:test_wip_zero_after_completion` |
| S7 | Units are dimension-compatible: kg↔g, L↔mL, packet↔carton (per pack spec). Mass↔volume raises unless the item has an explicit density. | SVC: `uom.domain.convert` · DB: `stock_lines` store base units only | `uom:test_round_trip_exact` (property), `uom:test_cross_dimension_raises` |
| S8 | WAC pools never drift: an issue takes `round(qty / pool_qty × pool_value)`; the last unit out takes the remaining value exactly. | SVC: `valuation.domain` | `valuation:test_wac_pool_drains_to_zero` (property) |

## Documents

| # | Invariant | Enforced | Test |
|---|---|---|---|
| D1 | Posted documents are immutable: posted stock lines, journals, receipts, runs, invoices, payments cannot be updated or deleted. Corrections are reversal journals or credit notes. | DB: trigger blocks UPDATE/DELETE when status is POSTED / COMPLETED (status-aware) | `db:test_posted_invoice_update_rejected`, `db:test_stock_line_delete_rejected`, `billing:test_credit_note_links_original` |
| D2 | Every production run freezes its recipe and pack spec: `recipe_snapshot`, `pack_snapshot` are written at start and never change; later recipe edits create a new version. | DB: trigger blocks snapshot updates · SVC: versions used by a run become immutable | `recipe:test_used_version_immutable`, `production:test_snapshot_frozen` |
| D3 | Invoice numbers are unique and gapless per organization and financial year, ≤ 16 characters. | DB: unique (org, invoice_no) · SVC: `number_sequences` row locked FOR UPDATE | `billing:test_parallel_invoice_numbers_gapless` |
| D4 | One idempotency key → one effect. A replay returns the first response; a different payload with the same key is rejected. | DB: unique (org, key) · SVC: request hash compare | `sales:test_offline_replay_single_order`, `procurement:test_duplicate_receipt_single_journal` |
| D5 | Payment allocations never exceed the payment: Σ allocations ≤ payment amount; Σ allocations per invoice ≤ invoice total. | DB: trigger on `payment_allocations` · SVC | `collections:test_over_allocation_rejected` |
| D6 | Invoice tax regime follows place of supply: same state → CGST + SGST (half each); different state → IGST. | SVC: `tax.domain` (pure) | `tax:test_tn_to_tn_split`, `tax:test_tn_to_ka_igst`, `bench:a08–a11`, `bench:a14` |
| D7 | Tax rates, thresholds, HSN, FSSAI, GSTIN, Udyam are effective-dated configuration, chosen by document date. | SVC: settings / tax_rules lookup by date | `tax:test_rate_change_by_date` |

## Platform

| # | Invariant | Enforced | Test |
|---|---|---|---|
| P1 | Period lock: no journal, invoice or payment may be posted into a locked period; reopening needs OWNER + reason (audited). | DB: trigger on insert checks `period_locks` · SVC | `ledger:test_post_into_locked_period_rejected` |
| P2 | Organization isolation: every business row carries `organization_id`; a session can read and write only its own organization. | DB: row-level security with `app.org_id` GUC set per request (ADR-0006) | `identity:test_cross_org_read_impossible` |
| P3 | Audit chain is unbroken: for each organization, `hash(n) = sha256(hash(n−1) ‖ canonical_json(row n))`. Every privileged mutation writes one row. | SVC: `audit.record()` in the same transaction, chain head locked · CLI: verify | `audit:test_tampered_row_detected` |
| P4 | RBAC on every route; the auditor can never mutate. | SVC: `require(perm)` dependency | `identity:test_route_role_matrix`, `identity:test_auditor_403_all_mutations` |
| P5 | No float in money or quantity paths. | SVC: `core.money` rejects float · CI grep gate · oracle loader yields Decimal | `test_core:test_float_is_rejected` (exists), CI `grep -rn "float(" backend/app/modules` |
| P6 | ML / analytics / LLM never write ledger, invoice, payment or run tables. | DB: analytics role has SELECT only on views | `analytics:test_role_is_read_only` (MP16) |

## Implemented in MP02 (database layer)

The DB-layer guards above now exist (migration `0003_guards.py`, RLS in `0004_rls_and_grants.py`, ADR-0009).
The actual test names, all in `backend/tests/db/`:

| Invariant | Guard | Tests |
|---|---|---|
| L1, L2 (value per journal) | deferred constraint triggers, SQLSTATE AH001 | `test_ledger_guards.py::test_unbalanced_journal_rejected`, `::test_unbalanced_value_rejected`, `::test_journal_without_lines_rejected`, `::test_nit_journals_balance_and_project` |
| Line roles (ADR-0002) | CHECK `sign_matches_role`; AH005 for value-only misuse | `::test_line_sign_must_match_role`, `::test_value_only_line_outside_true_up_rejected` |
| S1 | `inventory_balances` CHECK `store_not_negative` (per line) | `::test_store_cannot_go_negative` |
| S3 | projection trigger; app role has SELECT only | `::test_balanced_journal_posts_and_projects`, `::test_app_cannot_write_balances` |
| S4 | `source_type`, `source_id` NOT NULL + CHECK list; adjustments need reason + approver | `::test_adjustment_needs_reason` |
| D1 | no UPDATE/DELETE privilege (42501) and immutability triggers (AH002) | `::test_app_role_cannot_update_or_delete_stock_lines`, `::test_stock_line_update_or_delete_rejected_even_for_owner`, `test_document_guards.py::test_posted_invoice_update_rejected`, `::test_invoice_cancel_needs_reason_and_is_final`, `::test_invoice_line_is_insert_only`, `::test_receipt_lines_frozen_once_posted`, `test_ledger_guards.py::test_reversal_mirrors_and_restores_balance` |
| D2 | run and BOM-version triggers | `test_document_guards.py::test_run_snapshot_frozen_and_completed_run_locked`, `::test_recipe_lines_frozen_once_version_is_active` |
| D3 | `aahar_next_doc_number()` | `::test_doc_numbers_are_gapless_after_rollback`, `::test_parallel_doc_numbers_are_distinct_and_consecutive` |
| D5 | allocation trigger, AH004 | `::test_over_allocation_rejected`, `::test_invoice_with_payments_cannot_be_cancelled` |
| D6 (backstop) | CHECK `regime_follows_pos` | `::test_invoice_regime_must_follow_place_of_supply` |
| D7 | EXCLUDE no-overlap on `settings` and `tax_rules` | `::test_overlapping_tax_rules_rejected` |
| P1 | period-lock triggers, AH003 | `::test_post_into_locked_period_rejected` |
| P2 | RLS on 61 tables + composite FKs | `test_rls.py` (7 tests, incl. `::test_every_org_scoped_table_has_rls`) |
| Lots | (lot, item, org) composite FK | `test_ledger_guards.py::test_lot_must_belong_to_the_lines_item` |
| Schema | migrations up / down one / up; full down and up; models = migrations | `test_migrations.py` (3 tests) |
