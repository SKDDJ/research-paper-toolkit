# Deep Paper Review — Reference

Structured extraction from arXiv papers at two levels of depth.

## CLI

```bash
# Level 1 — quick metadata + method summary (~2-3k tokens, cheap model)
uv run python scripts/deep_review.py --paper <arxiv_id_or_url> --level 1 --profile config/profiles/<name>.yaml

# Level 2 — full extraction with framework mapping, formulas, figures, tables (~10-15k tokens, strong model)
uv run python scripts/deep_review.py --paper <arxiv_id_or_url> --level 2 --profile config/profiles/<name>.yaml
```

Accepts arXiv IDs (`2601.05536`), full URLs (`https://arxiv.org/abs/2601.05536`), or PDF URLs.

## Level 1 vs Level 2

| Aspect | Level 1 | Level 2 |
|--------|---------|---------|
| Input | Abstract + metadata | Full paper text (ar5iv HTML) |
| Model | Cheap (e.g., Haiku) | Strong (e.g., Opus) |
| Cost | ~2-3k tokens | ~10-15k tokens |
| Output | Metadata, method summary, experiments overview | + framework mapping, formulas, figures, tables, analysis |
| When to use | Quick screening, auto-trigger for high-scoring papers | User requests deep analysis, anchor/important papers |

## Output Files

- **JSON**: `data/reviews/{paper_id}.json` — structured extraction with source traceability on every claim
- **HTML**: `data/reports/reviews/{paper_id}_L{level}.html` — editorial-aesthetic report with MathJax formulas, ar5iv figures, rendered tables

## Extraction Schema (Key Fields)

**Both levels:** `metadata` (title, authors, affiliations, venue, year, code_url, doi), `method` (core_contribution, method_components, theoretical_results), `experiments` (datasets, baselines, metrics, key_results, settings)

**Level 2 only:** `method.framework_mapping` (maps to researcher's analytical framework), `method.key_formulas` (LaTeX), `experiments.key_figures` (with ar5iv image URLs), `experiments.key_tables` (with parsed row data), `analysis` (assumptions, limitations, anchor_cross_references)

## Paper Content Source

Primary: [ar5iv](https://ar5iv.labs.arxiv.org/) HTML with structured parsing — extracts tables (as row data + raw HTML), figures (as image URLs), formulas (as LaTeX from MathML alttext). Falls back to plain text if ar5iv unavailable.

Future (Phase 2): MineRU PDF parser for non-arXiv papers.

## Anti-Hallucination

- Every extracted claim includes a `source` field (section number, table ref, or "abstract")
- Missing info → `null` with `"source": "not_found"` — never fabricated
- Schema validation rejects results missing required source fields
