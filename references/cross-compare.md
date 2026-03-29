# Cross-Paper Comparison — Reference (Planned)

Compare multiple papers on shared datasets, metrics, and assumptions to identify research gaps.

## Planned CLI

```bash
# Compare specific papers
uv run python scripts/cross_compare.py --papers <id1> <id2> ... --profile config/profiles/<name>.yaml

# Compare all anchor papers
uv run python scripts/cross_compare.py --anchor-papers --profile config/profiles/<name>.yaml
```

## Planned Output

HTML dashboard at `data/reports/comparisons/` containing:
- Comparison matrices: shared datasets, metric differences, assumption conflicts
- Research gap identification (per Dr. Lan's requirements)
- Framework mapping overlay across papers

## Design Principles

- Only uses data from validated Level 1/Level 2 extractions — never generates new claims
- Comparison is purely data-driven: reads `data/reviews/{paper_id}.json` files
- Identifies where papers share experimental setup vs. where they diverge

## Status: Not yet implemented. Planned for Phase 1.5 (Priority 6).
