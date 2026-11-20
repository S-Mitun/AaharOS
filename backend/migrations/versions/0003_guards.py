"""Database-enforced guards: balanced journals, immutability, period locks, allocations, numbering, projection.

Error codes (SQLSTATE class AH, so services and tests can tell guards apart from ordinary errors):
  AH001  unbalanced journal (Σ qty per item ≠ 0, Σ value ≠ 0, or a journal with no lines)   law 1, law 2
  AH002  change to a posted / frozen record                                                  D1, D2
  AH003  posting into a locked period                                                        P1
  AH004  payment allocation over the payment or the invoice                                  D5
  AH005  value-only line outside a cost true-up or reversal                                  ADR-0002
A store going negative is a CHECK violation on `inventory_balances` (23514, invariant S1).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Insert-only tables: posted the moment they are written. Corrections are reversals or credit notes.
INSERT_ONLY = (
    "stock_journals",
    "stock_lines",
    "audit_log",
    "invoice_lines",
    "invoice_tax_lines",
    "credit_notes",
    "credit_note_lines",
    "credit_note_tax_lines",
    "payments",
    "payment_allocations",
    "material_issues",
    "material_issue_lines",
    "run_costs",
    "order_status_history",
    "dispatch_lines",
)

# (child table, parent table, FK column, parent statuses in which the child may still change)
FROZEN_WITH_PARENT = (
    ("purchase_receipt_lines", "purchase_receipts", "receipt_id", "DRAFT"),
    ("recipe_lines", "recipe_versions", "recipe_version_id", "DRAFT"),
    ("pack_spec_lines", "pack_spec_versions", "pack_spec_version_id", "DRAFT"),
    ("run_pack_lines", "production_runs", "run_id", "DRAFT,IN_PROGRESS"),
)

# (table, date column) checked against period_locks on insert
PERIOD_CHECKED = (
    ("stock_journals", "posting_date"),
    ("invoices", "invoice_date"),
    ("credit_notes", "note_date"),
    ("payments", "received_on"),
)

FUNCTIONS = r"""
-- ---------- shared helpers ----------
CREATE FUNCTION aahar_period_is_locked(p_org uuid, p_date date) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM period_locks
    WHERE organization_id = p_org AND period = date_trunc('month', p_date)::date
  )
$$;

CREATE FUNCTION aahar_same_except(p_old jsonb, p_new jsonb, p_allowed text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT (p_old - p_allowed) = (p_new - p_allowed)
$$;

-- ---------- law 1 and law 2: every journal balances (deferred to commit) ----------
CREATE FUNCTION aahar_check_journal_balanced() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_bad record;
  v_value numeric;
  v_kind text;
BEGIN
  SELECT item_id, sum(qty_base) AS qty INTO v_bad
    FROM stock_lines WHERE journal_id = NEW.journal_id
    GROUP BY item_id HAVING sum(qty_base) <> 0
    LIMIT 1;
  IF FOUND THEN
    RAISE EXCEPTION 'unbalanced journal %: quantity of item % sums to %, not 0',
      NEW.journal_id, v_bad.item_id, v_bad.qty USING ERRCODE = 'AH001';
  END IF;

  SELECT sum(value) INTO v_value FROM stock_lines WHERE journal_id = NEW.journal_id;
  IF v_value <> 0 THEN
    RAISE EXCEPTION 'unbalanced journal %: value sums to %, not 0', NEW.journal_id, v_value
      USING ERRCODE = 'AH001';
  END IF;

  IF NEW.line_role = 'VALUE_ONLY' THEN
    SELECT kind INTO v_kind FROM stock_journals WHERE id = NEW.journal_id;
    IF v_kind NOT IN ('COST_TRUE_UP', 'REVERSAL') THEN
      RAISE EXCEPTION 'journal %: value-only lines are allowed only in COST_TRUE_UP or REVERSAL journals, not %',
        NEW.journal_id, v_kind USING ERRCODE = 'AH005';
    END IF;
  END IF;
  RETURN NULL;
END
$$;

CREATE FUNCTION aahar_check_journal_has_lines() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM stock_lines WHERE journal_id = NEW.id) THEN
    RAISE EXCEPTION 'journal % has no lines', NEW.id USING ERRCODE = 'AH001';
  END IF;
  RETURN NULL;
END
$$;

-- stock_lines.posted_at is copied from the journal so the (org, item, location, posted_at) index needs no join.
CREATE FUNCTION aahar_stock_line_posted_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  SELECT posted_at INTO NEW.posted_at FROM stock_journals WHERE id = NEW.journal_id;
  RETURN NEW;
END
$$;

-- ---------- projection (ADR-0009): balances are maintained here and nowhere else ----------
-- Two steps, not one upsert: PostgreSQL checks CHECK constraints on the proposed INSERT row before it resolves
-- ON CONFLICT, so inserting the signed delta would reject every outgoing line. A zero row passes; the UPDATE then
-- applies the delta under the row lock and the store-not-negative CHECK judges the real new balance.
CREATE FUNCTION aahar_project_balance() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_kind text;
BEGIN
  SELECT kind INTO v_kind FROM locations WHERE id = NEW.location_id AND organization_id = NEW.organization_id;
  INSERT INTO inventory_balances
    (organization_id, item_id, location_id, lot_id, location_kind, qty_base, value)
  VALUES
    (NEW.organization_id, NEW.item_id, NEW.location_id, NEW.lot_id, v_kind, 0, 0)
  ON CONFLICT (organization_id, item_id, location_id, lot_id) DO NOTHING;
  UPDATE inventory_balances
     SET qty_base = qty_base + NEW.qty_base,
         value = value + NEW.value,
         updated_at = now()
   WHERE organization_id = NEW.organization_id
     AND item_id = NEW.item_id
     AND location_id = NEW.location_id
     AND lot_id IS NOT DISTINCT FROM NEW.lot_id;
  RETURN NULL;
END
$$;

-- ---------- D1: posted records are immutable ----------
CREATE FUNCTION aahar_forbid_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% on % is not allowed: posted records are immutable (post a reversal or a credit note)',
    TG_OP, TG_TABLE_NAME USING ERRCODE = 'AH002';
END
$$;

CREATE FUNCTION aahar_guard_invoice() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_allowed text[] := ARRAY['status', 'cancelled_at', 'cancel_reason'];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'invoice % cannot be deleted: cancel it or issue a credit note', OLD.invoice_no
      USING ERRCODE = 'AH002';
  END IF;
  IF NOT (OLD.status = 'POSTED' AND NEW.status = 'CANCELLED'
          AND aahar_same_except(to_jsonb(OLD), to_jsonb(NEW), v_allowed)) THEN
    RAISE EXCEPTION 'invoice % is posted: only POSTED -> CANCELLED (with a reason) is allowed; use a credit note',
      OLD.invoice_no USING ERRCODE = 'AH002';
  END IF;
  IF aahar_period_is_locked(OLD.organization_id, OLD.invoice_date) THEN
    RAISE EXCEPTION 'period % is locked: invoice % cannot be cancelled', to_char(OLD.invoice_date, 'YYYY-MM'),
      OLD.invoice_no USING ERRCODE = 'AH003';
  END IF;
  IF EXISTS (SELECT 1 FROM payment_allocations WHERE invoice_id = OLD.id) THEN
    RAISE EXCEPTION 'invoice % has payments allocated: issue a credit note instead of cancelling', OLD.invoice_no
      USING ERRCODE = 'AH002';
  END IF;
  RETURN NEW;
END
$$;

-- D2: a run's snapshots never change once written; a finished run changes only its cost status or reversal.
CREATE FUNCTION aahar_guard_run() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'DRAFT' THEN
      RETURN OLD;
    END IF;
    RAISE EXCEPTION 'run % is %: only a DRAFT run can be deleted', OLD.run_no, OLD.status USING ERRCODE = 'AH002';
  END IF;

  IF (OLD.recipe_snapshot IS NOT NULL AND NEW.recipe_snapshot IS DISTINCT FROM OLD.recipe_snapshot)
     OR (OLD.pack_snapshot IS NOT NULL AND NEW.pack_snapshot IS DISTINCT FROM OLD.pack_snapshot) THEN
    RAISE EXCEPTION 'run %: the recipe and pack snapshots are frozen once the run starts', OLD.run_no
      USING ERRCODE = 'AH002';
  END IF;

  IF NEW.status <> OLD.status AND NOT (
       (OLD.status = 'DRAFT' AND NEW.status IN ('IN_PROGRESS', 'CANCELLED'))
    OR (OLD.status = 'IN_PROGRESS' AND NEW.status IN ('COMPLETED', 'CANCELLED'))
    OR (OLD.status = 'COMPLETED' AND NEW.status = 'REVERSED')) THEN
    RAISE EXCEPTION 'run %: status % -> % is not allowed', OLD.run_no, OLD.status, NEW.status
      USING ERRCODE = 'AH002';
  END IF;

  IF NEW.cost_status <> OLD.cost_status AND NOT (OLD.cost_status = 'PROVISIONAL' AND NEW.cost_status = 'FINAL') THEN
    RAISE EXCEPTION 'run %: cost status % -> % is not allowed', OLD.run_no, OLD.cost_status, NEW.cost_status
      USING ERRCODE = 'AH002';
  END IF;

  IF OLD.status IN ('COMPLETED', 'REVERSED', 'CANCELLED')
     AND NOT aahar_same_except(to_jsonb(OLD), to_jsonb(NEW), ARRAY['status', 'cost_status']) THEN
    RAISE EXCEPTION 'run % is %: only its cost status or a reversal may change', OLD.run_no, OLD.status
      USING ERRCODE = 'AH002';
  END IF;
  RETURN NEW;
END
$$;

-- Documents with a DRAFT stage (receipts): free while DRAFT, then only POSTED -> REVERSED.
CREATE FUNCTION aahar_guard_receipt() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'DRAFT' THEN
      RETURN OLD;
    END IF;
    RAISE EXCEPTION 'receipt % is %: it cannot be deleted', OLD.receipt_no, OLD.status USING ERRCODE = 'AH002';
  END IF;
  IF OLD.status = 'DRAFT' THEN
    RETURN NEW;
  END IF;
  IF OLD.status = 'POSTED' AND NEW.status = 'REVERSED'
     AND aahar_same_except(to_jsonb(OLD), to_jsonb(NEW), ARRAY['status']) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'receipt % is %: only POSTED -> REVERSED is allowed', OLD.receipt_no, OLD.status
    USING ERRCODE = 'AH002';
END
$$;

-- Recipe and pack spec versions: free while DRAFT; an ACTIVE version may only be RETIRED.
CREATE FUNCTION aahar_guard_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'DRAFT' THEN
      RETURN OLD;
    END IF;
    RAISE EXCEPTION '% version % is %: it cannot be deleted', TG_TABLE_NAME, OLD.version, OLD.status
      USING ERRCODE = 'AH002';
  END IF;
  IF OLD.status = 'DRAFT' THEN
    RETURN NEW;
  END IF;
  IF OLD.status = 'ACTIVE' AND NEW.status IN ('ACTIVE', 'RETIRED')
     AND aahar_same_except(to_jsonb(OLD), to_jsonb(NEW), ARRAY['status']) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION '% version % is %: create a new version instead', TG_TABLE_NAME, OLD.version, OLD.status
    USING ERRCODE = 'AH002';
END
$$;

-- Lines of a parent document may change only while the parent is in an open status.
-- TG_ARGV: parent table, FK column, comma-separated open statuses.
CREATE FUNCTION aahar_guard_child_of_open_parent() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_open text[] := string_to_array(TG_ARGV[2], ',');
  v_row jsonb;
  v_status text;
BEGIN
  FOREACH v_row IN ARRAY (
    CASE TG_OP
      WHEN 'INSERT' THEN ARRAY[to_jsonb(NEW)]
      WHEN 'DELETE' THEN ARRAY[to_jsonb(OLD)]
      ELSE ARRAY[to_jsonb(OLD), to_jsonb(NEW)]
    END)
  LOOP
    EXECUTE format('SELECT status FROM %I WHERE id = $1', TG_ARGV[0])
      INTO v_status USING (v_row ->> TG_ARGV[1])::uuid;
    IF v_status IS NOT NULL AND NOT (v_status = ANY (v_open)) THEN
      RAISE EXCEPTION '% on %: its % is %, so its lines are frozen', TG_OP, TG_TABLE_NAME, TG_ARGV[0], v_status
        USING ERRCODE = 'AH002';
    END IF;
  END LOOP;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
$$;

-- ---------- P1: no posting into a locked period. TG_ARGV[0] = the document's date column ----------
CREATE FUNCTION aahar_check_period_open() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_date date := (to_jsonb(NEW) ->> TG_ARGV[0])::date;
BEGIN
  IF aahar_period_is_locked(NEW.organization_id, v_date) THEN
    RAISE EXCEPTION 'period % is locked: cannot post to %', to_char(v_date, 'YYYY-MM'), TG_TABLE_NAME
      USING ERRCODE = 'AH003';
  END IF;
  RETURN NEW;
END
$$;

-- ---------- D5: allocations never exceed the payment or the invoice ----------
-- SECURITY DEFINER so it can lock the payment and invoice rows (the app role cannot UPDATE payments).
-- The composite FKs already guarantee both rows belong to NEW.organization_id.
CREATE FUNCTION aahar_check_allocation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_pay record;
  v_inv record;
  v_used numeric;
BEGIN
  SELECT id, customer_id, amount INTO v_pay FROM payments
    WHERE id = NEW.payment_id AND organization_id = NEW.organization_id FOR UPDATE;
  SELECT id, customer_id, total, status, invoice_no INTO v_inv FROM invoices
    WHERE id = NEW.invoice_id AND organization_id = NEW.organization_id FOR UPDATE;
  IF v_pay.id IS NULL OR v_inv.id IS NULL THEN
    RETURN NEW;  -- the foreign keys reject it
  END IF;
  IF v_inv.status <> 'POSTED' THEN
    RAISE EXCEPTION 'invoice % is %: payments cannot be allocated to it', v_inv.invoice_no, v_inv.status
      USING ERRCODE = 'AH004';
  END IF;
  IF v_pay.customer_id <> v_inv.customer_id THEN
    RAISE EXCEPTION 'payment and invoice % belong to different customers', v_inv.invoice_no USING ERRCODE = 'AH004';
  END IF;

  SELECT coalesce(sum(amount), 0) INTO v_used FROM payment_allocations WHERE payment_id = NEW.payment_id;
  IF v_used + NEW.amount > v_pay.amount THEN
    RAISE EXCEPTION 'allocations % + % exceed payment amount %', v_used, NEW.amount, v_pay.amount
      USING ERRCODE = 'AH004';
  END IF;

  SELECT coalesce(sum(amount), 0) INTO v_used FROM payment_allocations WHERE invoice_id = NEW.invoice_id;
  IF v_used + NEW.amount > v_inv.total THEN
    RAISE EXCEPTION 'allocations % + % exceed invoice % total %', v_used, NEW.amount, v_inv.invoice_no, v_inv.total
      USING ERRCODE = 'AH004';
  END IF;
  RETURN NEW;
END
$$;

-- ---------- D3: gapless document numbers per (org, doc type, FY) ----------
-- The upsert locks the counter row until commit; a rolled-back transaction rolls the counter back too.
CREATE FUNCTION aahar_next_doc_number(p_org uuid, p_doc_type text, p_fy text) RETURNS bigint
LANGUAGE sql VOLATILE AS $$
  INSERT INTO number_sequences AS s (organization_id, doc_type, fy, next_value)
  VALUES (p_org, p_doc_type, p_fy, 2)
  ON CONFLICT (organization_id, doc_type, fy) DO UPDATE SET next_value = s.next_value + 1
  RETURNING s.next_value - 1
$$;
"""

DROP_FUNCTIONS = (
    "aahar_next_doc_number(uuid, text, text)",
    "aahar_check_allocation()",
    "aahar_check_period_open()",
    "aahar_guard_child_of_open_parent()",
    "aahar_guard_version()",
    "aahar_guard_receipt()",
    "aahar_guard_run()",
    "aahar_guard_invoice()",
    "aahar_forbid_change()",
    "aahar_project_balance()",
    "aahar_stock_line_posted_at()",
    "aahar_check_journal_has_lines()",
    "aahar_check_journal_balanced()",
    "aahar_same_except(jsonb, jsonb, text[])",
    "aahar_period_is_locked(uuid, date)",
)


def _triggers() -> list[tuple[str, str, str]]:
    """(trigger name, table, CREATE statement) for every trigger this revision adds."""
    out: list[tuple[str, str, str]] = [
        (
            "trg_stock_lines_balanced",
            "stock_lines",
            "CREATE CONSTRAINT TRIGGER trg_stock_lines_balanced AFTER INSERT ON stock_lines"
            " DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION aahar_check_journal_balanced()",
        ),
        (
            "trg_stock_journals_have_lines",
            "stock_journals",
            "CREATE CONSTRAINT TRIGGER trg_stock_journals_have_lines AFTER INSERT ON stock_journals"
            " DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION aahar_check_journal_has_lines()",
        ),
        (
            "trg_stock_lines_posted_at",
            "stock_lines",
            "CREATE TRIGGER trg_stock_lines_posted_at BEFORE INSERT ON stock_lines"
            " FOR EACH ROW EXECUTE FUNCTION aahar_stock_line_posted_at()",
        ),
        (
            "trg_stock_lines_project",
            "stock_lines",
            "CREATE TRIGGER trg_stock_lines_project AFTER INSERT ON stock_lines"
            " FOR EACH ROW EXECUTE FUNCTION aahar_project_balance()",
        ),
        (
            "trg_invoices_guard",
            "invoices",
            "CREATE TRIGGER trg_invoices_guard BEFORE UPDATE OR DELETE ON invoices"
            " FOR EACH ROW EXECUTE FUNCTION aahar_guard_invoice()",
        ),
        (
            "trg_production_runs_guard",
            "production_runs",
            "CREATE TRIGGER trg_production_runs_guard BEFORE UPDATE OR DELETE ON production_runs"
            " FOR EACH ROW EXECUTE FUNCTION aahar_guard_run()",
        ),
        (
            "trg_purchase_receipts_guard",
            "purchase_receipts",
            "CREATE TRIGGER trg_purchase_receipts_guard BEFORE UPDATE OR DELETE ON purchase_receipts"
            " FOR EACH ROW EXECUTE FUNCTION aahar_guard_receipt()",
        ),
        (
            "trg_payment_allocations_limit",
            "payment_allocations",
            "CREATE TRIGGER trg_payment_allocations_limit BEFORE INSERT ON payment_allocations"
            " FOR EACH ROW EXECUTE FUNCTION aahar_check_allocation()",
        ),
    ]
    for table in ("recipe_versions", "pack_spec_versions"):
        out.append(
            (
                f"trg_{table}_guard",
                table,
                f"CREATE TRIGGER trg_{table}_guard BEFORE UPDATE OR DELETE ON {table}"
                " FOR EACH ROW EXECUTE FUNCTION aahar_guard_version()",
            )
        )
    for table in INSERT_ONLY:
        out.append(
            (
                f"trg_{table}_immutable",
                table,
                f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table}"
                " FOR EACH ROW EXECUTE FUNCTION aahar_forbid_change()",
            )
        )
    for child, parent, fk, statuses in FROZEN_WITH_PARENT:
        out.append(
            (
                f"trg_{child}_frozen",
                child,
                f"CREATE TRIGGER trg_{child}_frozen BEFORE INSERT OR UPDATE OR DELETE ON {child}"
                f" FOR EACH ROW EXECUTE FUNCTION aahar_guard_child_of_open_parent('{parent}', '{fk}', '{statuses}')",
            )
        )
    for table, column in PERIOD_CHECKED:
        out.append(
            (
                f"trg_{table}_period_open",
                table,
                f"CREATE TRIGGER trg_{table}_period_open BEFORE INSERT ON {table}"
                f" FOR EACH ROW EXECUTE FUNCTION aahar_check_period_open('{column}')",
            )
        )
    return out


def upgrade() -> None:
    op.execute(FUNCTIONS)
    for _name, _table, create in _triggers():
        op.execute(create)


def downgrade() -> None:
    for name, table, _create in reversed(_triggers()):
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
    for signature in DROP_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
