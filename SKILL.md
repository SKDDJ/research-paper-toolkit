---
name: research-paper-toolkit
description: >-
  Research paper deep review, taxonomy management, and cross-paper comparison toolkit.
  Use when the user asks to "deep review a paper", "analyze paper", "extract paper",
  provides an arXiv ID or URL, asks to "bookmark" or "dismiss" a paper, requests a
  "cross-comparison", or mentions taxonomy management. Also use when the user asks
  about paper extraction, research gap identification, or structured paper analysis.
---

# Research Paper Toolkit

Structured paper extraction, taxonomy management, and cross-paper comparison. Profile-driven — all researcher-specific configuration lives in `config/profiles/<name>.yaml`.

## Quick Reference

| Capability | Command | Details |
|------------|---------|---------|
| **Deep Review** | `uv run python scripts/deep_review.py --paper <id> --level <1\|2> --profile config/profiles/<name>.yaml` | See `references/deep-review.md` |
| **Taxonomy** | `uv run python scripts/taxonomy.py <action> ...` | See `references/taxonomy.md` (planned) |
| **Cross-Compare** | `uv run python scripts/cross_compare.py --papers ...` | See `references/cross-compare.md` (planned) |

## Deep Review (Working)

Two-level extraction from arXiv papers:
- **Level 1**: Cheap model, abstract-only → metadata + method summary (~2-3k tokens)
- **Level 2**: Strong model, full paper text → framework mapping + formulas + figures + tables + analysis (~10-15k tokens)

Output: JSON (`data/reviews/`) + HTML report (`data/reports/reviews/`). For full details including schema fields and extraction options, read `references/deep-review.md`.

## Profile System

Each researcher has a profile YAML defining: research scope, anchor papers, analytical framework, scoring criteria, and LLM preferences. For the complete field reference and how to create a new profile, read `references/profile-system.md`.

## Taxonomy Management (Planned)

Hierarchical, multi-label paper organization: bookmark, dismiss, categorize. Read `references/taxonomy.md` for the planned interface.

## Cross-Paper Comparison (Planned)

Compare papers on shared datasets, metrics, and assumptions. Identifies research gaps. Read `references/cross-compare.md` for the planned interface.

## Anti-Hallucination Rules

- Every extracted claim MUST include a `source` field (section number, table ref, or "abstract")
- Missing info → `null` with `"source": "not_found"` — NEVER fabricate
- Cross-paper comparisons only use validated Level 1/Level 2 extraction data

## Data Layout

```
config/profiles/<name>.yaml   — researcher profiles
data/reviews/{paper_id}.json  — extraction results
data/reports/reviews/          — HTML reports
data/taxonomy.json             — taxonomy tree (planned)
data/preferences.jsonl         — preference log (planned)
```
