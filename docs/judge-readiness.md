# Judge readiness (MP19 red-team review, 2026-11-26)

Reviewed as a strict evaluator. Each line says pass or fail and the evidence; nothing is marked pass without a command
or test that ran.

## 1. Fresh clone, following the README
| Check | Result | Evidence |
|---|---|---|
| A fresh clone has everything it needs (no untracked file) | pass | cloned `feat/mp13-traceability` into an empty folder: the production image built in 95 s; `docker compose config` valid |
| The README's 4 local commands | pass (with friction) | `make up`, `make migrate`, `make seed-demo`, `make benchmark` are the same targets CI and this review ran |
| Friction | noted | Windows needs `make` (one `winget` line, in the README); the first `make up` builds images for several minutes; ports 5180 / 8180 / 5442 must be free |

## 2. Benchmark and Explain trails
| Check | Result | Evidence |
|---|---|---|
| 26 rows against the oracle | pass, 26/26 | `make benchmark` (runner output in this review), oracle integrity 10/10 |
| The same figures through the HTTP API on a sandbox | pass | `tests/db/test_full_pipeline.py`: 238 / 88, ₹7,875.00, ₹3,875.00, ₹5,855.00, ₹31.14 |
| The same figures typed in the browser | pass | `e2e/tests/production.spec.ts`: ₹43.13/kg, 160 → 120 kg, −6.00%, ₹5,855.00, ₹31.14 |
| Explain trails on UI numbers | pass (by test) | every figure is rendered by `Num` from an `Explained` payload with its inputs and source ids; the trails were checked through tests and live screens, not one by one by hand |

## 3. Hunts
| Hunt | Result | Evidence |
|---|---|---|
| Floats in money or quantity paths | pass | `grep -rn "float(" backend/app/modules`: one hit, the haversine trigonometry in transport (rounded to a Decimal at once; ADR-0021); float inputs are refused by tests |
| A UI number not from the database | pass, one accepted | the batch card's "in store → after" preview subtracts what the user is typing from the store balance; it is a preview, never stored |
| Endpoints without RBAC | pass | `tests/db/test_rbac.py`: every route guarded or listed as public with a reason; the auditor gets 403 on every write |
| Writable posted documents | pass | database triggers; `test_invoice_lines_are_immutable`, `test_document_guards.py`, insert-only grants |
| A path to negative stock | pass | store balances cannot go below zero (projection check + available-to-promise); `test_refused_post_leaves_no_trace_and_the_session_stays_usable`, the state-machine property test |
| Placeholders described as done | pass | every registered screen is built; mocks (e-way bill, IRP, UPI QR) and synthetic analytics are labelled in the UI and README |
| Tamil overflow | not checked | Tamil covers the app's frame only; long Tamil labels in the sidebar were not reviewed on a phone (see gaps) |
| Broken exports | pass | `tests/db/test_reports.py` (CSV, XLSX, GSTR-1 JSON, evidence ZIP, Tally XML) |

## 4. Attack drills (each is a test that ran in this review)
| Drill | Result | Test |
|---|---|---|
| Duplicate offline sync | pass | `e2e` "a duplicate send is replayed, never doubled"; `test_duplicate_key_replayed_and_reused_key_conflicts` |
| Racing approvals for the last packets | pass | `test_parallel_approvals_cannot_over_reserve` |
| Failure in the middle of a run posting | pass | `test_failure_at_any_write_persists_nothing` |
| Tampered audit row | pass | `test_any_edited_row_breaks_the_chain`, `test_deleted_newest_row_is_caught_by_the_chain_head` |
| Tampered stock balance | pass | `test_projection_diff_catches_a_tampered_balance` |
| Posting into a locked month | pass | `test_post_into_locked_period_rejected`, `test_locked_period_is_refused` |
| Credit note larger than what is left | pass | `test_credit_note_cannot_exceed_what_is_left`, law 4 with a credit note and a cancelled invoice |
| Dispatching an expired lot | pass | `test_expired_lots_are_not_available_to_promise`, `test_not_enough_unexpired_stock` |
| Over-allocating a payment | pass | `test_over_allocation_rejected` |
| A forged batch-passport token | pass | `test_forged_altered_or_foreign_tokens_are_refused` |
| A write from another site | pass | `test_a_write_from_another_site_is_refused` |

## 5. Live-change drills (Part F)
| Change | Result | Evidence |
|---|---|---|
| 500 g pack | pass | `test_a_500g_run_from_seed_data` (yield −2.50%, cartons of 10) |
| Tolerance 2% | **failed, fixed** | a new value overlapped the open-ended setting and was refused. Fixed: a new value supersedes the old from its date (`effective_settings.put`), and `PUT /api/settings/{key}` (`settings.manage`). `test_changes_apply_from_their_date_and_never_rewrite_the_past`: B-001 keeps its frozen 3% |
| New GST rate | **failed, fixed** | same overlap for tax rules. Fixed in `tax.create_rule`; invoice A keeps 5% and ₹7,875.00 |
| Customer's own price | pass | a customer price list version from a date; the old orders keep the price they captured |
| FIFO as the posting policy | not supported (by design) | WAC posts; FIFO and last price are shown beside it (ADR-0012); switching the posting method is not built |
| Sales return (stock back) | gap | credit notes are value-only; returned packets are not put back into stock |
| Carton of 24 | gap | a quantity of 1/24 per packet is not exact at 6 dp, so it is refused; cartons of 20 and 10 work |
| The benchmark after the changes | pass | 26/26 (the changes are on their own tenant; the replay builds a fresh one) |

## 6. Defects by severity
- **Major, fixed:** settings and GST rates could not be changed once set (overlap refused). Fixed with supersede-on-save
  and a settings route; tested.
- **Minor, fixed:** white text on the turmeric accent failed WCAG AA contrast (3.8:1); scrollable tables were not
  keyboard-reachable (axe in Playwright).
- **Accepted, documented:** Starlette 0.41 advisories (the FastAPI upgrade breaks request handling the RBAC tests
  rely on; a separate change); two moderate React Router advisories (need v7); the tour gate lives in the browser.
- **Gaps:** sales returns into stock, FIFO posting, cartons of 24, Tamil beyond the frame, analytics UI, LightGBM.

## 7. The 12 hardest panel questions
1. **Why divide by 188, not 200?** Only good packets can be sold: ₹5,855 / 188 = ₹31.14. Dividing by 200 hides about
   ₹2.29 of loss per packet.
2. **Why weighted average?** Flour is fungible and the brief's opening-plus-purchase case fits it. FIFO (₹30.90) and
   last price (₹31.54) are shown beside it, and history is never revalued.
3. **How do you know the balances are right?** Every movement is a zero-sum journal enforced by a database trigger;
   balances are a projection that `make integrity` rebuilds and compares; a property test runs random sequences.
4. **What if two admins approve the last packets at once?** The stock row is locked inside the approval transaction;
   the race test proves one wins and the other sees the shortage.
5. **What does your ML actually do?** It advises only, on synthetic data: festival-aware demand beats seasonal-naive
   (WAPE 24.3% vs 57.1%), EWMA flags operator O-3's oil drift, a bootstrap flags supplier S-05. It never writes to the
   books and has no screen yet.
6. **What is mocked?** GST filing, IRP, the e-way bill and the UPI QR are mock adapters; GSTIN, FSSAI, HSN, RUCO, TPC
   and Legal Metrology figures are DEMO settings to verify.
7. **Why does the pouch show a problem when fewer than 200 were used?** Packaging is consumed per good packet: 188
   good need 188 pouches; 194 used is +3.19%.
8. **How does a recall find the right batches when raw stock is not lot-tracked?** A supplier lot may be in every
   issue after it arrived until the store ran empty: a recall can name an extra batch, never miss one (property test).
9. **What stops someone editing a posted invoice?** Database triggers and grants: posted rows cannot be updated or
   deleted; corrections are new documents (cancellation, credit note, reversal), all in the hash-chained audit.
10. **Offline duplicates?** The phone makes the idempotency key; the server replays the original response.
11. **Why one monolith, not microservices?** One factory, one database, transactions across stock, tax and audit;
    modules talk through service interfaces and an import-linter contract keeps the layers honest.
12. **What would you do next?** Sales returns into stock, a fluent review of Tamil, the FastAPI upgrade, a real
    pilot with baselines for the impact metrics.
