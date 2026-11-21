# ADR-0013: The production run, frozen snapshots and the variance engine

- Status: Accepted (MP06, 2026-11-21; plan and decisions E1–E4 approved by the user the same day)
- Builds on: ADR-0002 (WIP between issue and completion), ADR-0003 (two-level driver BOM), ADR-0011 (posting rules),
  ADR-0012 (valuation read from the ledger)

## Context
MP06 builds `recipe` (versioned recipes and pack specs) and `production` (runs, material issues, the atomic
completion, the variance engine and the mass balance). The benchmark replay's J2 and J3 now go through these services
instead of a stand-in. Four decisions were approved before building (E1–E4); the rest of this ADR records the rules
the code follows.

## Decision

### E1. Quantity variances are computed on read, not stored
- A run freezes, when it **starts**, a `recipe_snapshot` (header, bulk item, bulk yield, every line in base units with
  its tolerance override) and a `pack_snapshot` (`{"versions": {pack spec version id: snapshot}}`: net g, units per
  carton, shelf life, FG item and its stock unit, the recipe it packs, every packaging line). The recipe snapshot also
  carries `variance_tolerance_pct`, the organization setting in force on the run date, and the date it was read.
- Yield and usage variances, packing and the mass balance are pure functions (`production.domain`) of that snapshot
  and the run's posted actuals (net material issues, pack-line results, samples, scrap and loss). They are
  deterministic and cannot drift, the same idea as ADR-0012. `variance_results` (owned by `costing`, with a NOT NULL
  rupee column) stays unused; MP07 decides whether costed rows are stored.

### E2. Flag = beyond tolerance and unfavourable
- `flagged = |pct| > tolerance AND unfavourable`, compared on the **exact** percentage, so exactly 3.00% is not
  flagged and 3.001% (shown as 3.00) is. The display rounds half up to 2 dp.
- Unfavourable: usage above standard; yield below expected. Favourable beyond tolerance is information, not an alert;
  on the carton line (qty per good unit × units per carton = 1) it gets the note "8 loose packets not cartoned".
- Tolerance = the line's override, else the frozen organization setting. A zero standard has no percentage; any use
  against it is beyond tolerance.
- Packaging is shown in two views: the **flexible** standard (qty per good unit × good units), which drives the alert,
  and the **batch view** (× expected units), shown alongside and never flagged (pouch +3.19% vs −3.00%).

### E3. Numbers
- Runs B-001, B-002, … per organization: `aahar_next_doc_number(org, 'RUN', '00-00')`, a perpetual sequence, taken
  when the DRAFT is created.
- Lot no. = run no.; a run with several pack lines gets -A, -B, … (at most 26 pack lines).
- Material issues and returns share `MI/26-27/000001`, gapless per financial year.
- Pack lines are ordered by (pack spec code, version). That order decides the lot suffix and which line takes the
  rounding remainder, and it is stable because a pack spec version may appear only once in a run.

### E4. A pack line with no good units writes its cost off to SCRAP
- Its share of the ingredient value leaves PRODUCTION as the **bulk item** to SCRAP (qty = bulk allocated, value =
  share), and any packaging it used goes to SCRAP at its value. A reason is required. Law 2 holds and nothing is
  silent. The same rule applies to packaging that cannot be absorbed (every unit used was damaged).

### Version workflow
- DRAFT → ACTIVE → RETIRED. Activating a version retires the version that was ACTIVE, with an audit row.
- Lines are frozen by the existing DB trigger once a version leaves DRAFT, and only ACTIVE versions can create or start
  a run, so "a version used by a run is immutable" holds by construction (tested, AH002).
- A recipe makes a BULK item weighed in grams; recipe lines take RAW items, pack lines PACK items; quantities per good
  unit must be exact at 6 dp (1/24 carton is refused; the 500 g seed uses 10 per carton, so 1/10 is exact).

### Material issues
- An issue posts RAW_STORE → WIP at WAC through `valuation.issue_value` (the per-(item, store) lock is taken before
  the pool is read). A return posts WIP → RAW_STORE at the **run's own issued average** (its net issued value ×
  qty / net issued qty, the last unit takes the rest), never the WIP average shared with other runs.
- The ledger journal is posted first with the issue's pre-generated id as its source, then the insert-only
  `material_issues` row (which needs the journal id) and its lines.

### The completion, atomic in one savepoint
1. claim the Idempotency-Key (a replay returns the first completion; the status check happens after the key, so a
   tablet that retries after a lost response gets the original answer)
2. lock the run row, require IN_PROGRESS
3. one FG lot per pack line with good units: mfg = run date, best-before = run date + shelf life
4. packaging valued at WAC once per item over all pack lines (so the pool's last-unit rule holds), split by quantity
5. one RUN_COMPLETION journal:
   - the run's net issues WIP → PRODUCTION at the value they were issued (so WIP returns to zero, S6)
   - packaging PACK_STORE → PRODUCTION at WAC, damaged units → SCRAP at no value (the cost stays in good output)
   - FG PRODUCTION → FG_STORE per lot; process scrap as bulk PRODUCTION → SCRAP at no value
6. pack lines (good units, packaging used, damage, lot), fill-weight samples, the oil session
7. the run → COMPLETED with scrap, loss and reason in a single update, then the audit row

Any refusal rolls the savepoint back. `tests/db/test_production.py` injects a failure at the third write, and then at
every write of a completion in turn, and checks that no journal, lot, pack-line change, sample, oil session, status
change, audit row or balance change is left behind, and that a clean retry then succeeds.

### Value split and rounding (ADR-0003)
- Lot value = its share of the ingredient value (split by bulk allocated, rounded half up to paise, the last line
  takes the remainder) + its own packaging value. Σ lot values + Σ written off = ingredients + packaging, exactly.

### Mass balance (law 3)
- expected bulk = good units × net + recorded scrap + recorded loss + **unexplained gap**, shown and never forced to
  zero. Giveaway = (mean sampled net − declared net) × good units, shown as part of the gap.
- Fill-weight samples are recorded per run (the table has no pack-line column), so they are accepted for
  single-pack-line runs only (known gap).

### API and permissions
- `GET /api/recipes`, `GET /api/pack-specs`, `GET /api/runs`, `GET /api/runs/{id}`: `report.read`. The plan listed
  recipe reads under `recipe.manage`; reading is `report.read` instead so auditors can read the standards behind a
  variance. Creating recipes, pack specs and versions and activating them: `recipe.manage`.
- `POST /api/runs`, `/start`, `/issues`: `run.start`. `POST /api/runs/{id}/complete`: `run.complete`.
- Quantities arrive as decimal strings (a JSON number is a 422); issues and completion honour `Idempotency-Key`.

### Integrity
- `make integrity` adds S6: for every COMPLETED run, the WIP lines of its material issues and its completion journal
  sum to zero per item in quantity and value, and the run has a completion journal. It also reports (never fails) the
  mass-balance gap of each completed run.

## Consequences
- The 500 g pack and mixed splits are data: a DB test runs a 500 g run and a 200 g + 500 g split from seed data with no
  code change, and `production.domain` mentions no product, pack size or carton size (a test reads its source).
- Benchmark assertions 4, 6, 7 and 20 are green (9/26). B-001 = ₹4,055.00 materials (PROVISIONAL; MP07 adds labour and
  gas through a true-up).
- MP07 reads the same snapshot and actuals for the waterfall and the run cost. Run reversal (`run.reverse`) is not
  built yet.
