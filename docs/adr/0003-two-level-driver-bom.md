# ADR-0003: Two-level BOM (recipe + pack spec) with drivers

- Status: Accepted (MP01, approved 2026-11-21)

## Context
The brief's BOM lists ingredients and packaging together "per batch", but packaging is consumed per packet actually
made. The interview asks for a 500 g pack "sharing the same BOM".

## Decision
- **Recipe** (versioned): ingredient lines with driver `PER_BATCH` and a bulk yield (40,000 g per batch).
- **Pack spec** (versioned, linked to a recipe and an FG item): net grams per unit, units per carton, shelf life,
  and packaging lines with driver `PER_GOOD_UNIT`.
- A **run** is one recipe execution × batch multiplier plus one or more pack lines, each with the bulk allocated to it.
  Expected units = bulk allocated ÷ net weight.
- Variances: ingredients against the batch standard; packaging against the flexible standard for actual good units.
  Both views are shown.
- Multi-pack runs split ingredient and conversion cost between lots by bulk allocated; packaging cost goes to its
  own pack line.
- Runs freeze `recipe_snapshot` and `pack_snapshot`; versions used by a run become immutable.

## Consequences
- A 500 g pack, mixed splits and a carton of 24 are configuration rows (`docs/architecture/bom.md` §4).
- The pouch damage that the batch view hides (−3.00%) is flagged by the flexible view (+3.19%).
- Rejected: one flat BOM per SKU (a 500 g pack would duplicate the recipe and drift); hard-coded pack sizes.
