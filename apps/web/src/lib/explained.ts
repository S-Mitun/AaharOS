/** An `Explained` value as the API serialises it (MASTER_PACK B.6): every number a string, never a float. */
export interface ExplainedInput {
  label: string;
  value: string;
  unit: string;
  source: { type: string; id: string } | null;
}

export interface Explained {
  value: string;
  unit: string;
  formula: string;
  method: string | null;
  inputs: ExplainedInput[];
}

/** Decimals to show for a unit: rupees to paise, percentages to 2 dp, quantities as they come. */
export function displayPlaces(unit: string): number | null {
  if (unit === "INR" || unit.startsWith("INR/") || unit === "%") return 2;
  return null;
}

const SOURCE_LABEL: Record<string, string> = {
  production_run: "Production run",
  run_cost: "Run cost entry",
  stock_journal: "Stock movement",
  standard_cost_card: "Standard cost card",
  inventory_balances: "Stock balance",
  purchase_receipt: "Purchase receipt",
  oracle: "expected values",
  invoice: "Invoice",
  payment: "Payment",
};

export function sourceLabel(type: string): string {
  return SOURCE_LABEL[type] ?? type.replace(/_/g, " ");
}
