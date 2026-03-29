# Cross-Paper Comparison — Reference

Compare multiple papers side-by-side to identify research gaps, shared evaluation settings, and framework coverage.

## CLI

```bash
# Compare all anchor papers from profile
uv run python scripts/cross_compare.py --anchor-papers --profile config/profiles/<name>.yaml

# Compare specific papers by arXiv ID
uv run python scripts/cross_compare.py --papers 2509.02896 2601.05536 --profile config/profiles/<name>.yaml
```

Requires Level 2 extraction JSONs in `data/reviews/`. Run `deep_review.py --batch-anchor --level 2` first.

## Output

HTML dashboard at `data/reports/comparisons/comparison_YYYY-MM-DD.html` containing:

### Sections

1. **Paper Overview** — all compared papers with title, venue, year, summary
2. **Research Gaps & Opportunities** — auto-identified gaps (see below)
3. **Framework Mapping Overlay** — each paper's choice per framework layer, sparse layers highlighted
4. **Dataset Coverage Matrix** — papers × datasets with ✓/✗
5. **Baseline Usage** — which papers compare against which baselines
6. **Metrics Used** — which metrics each paper reports
7. **Assumptions** — explicit and implicit assumptions across papers
8. **Limitations** — author-stated and inferred limitations
9. **Cross-References** — citation relationships between compared papers

### Research Gap Identification

Automatically surfaces:
- **Framework gaps** — layers addressed by <1/3 of papers (potential research blind spots)
- **Evaluation gaps** — datasets used by only one paper (no cross-comparison possible)
- **Comparison opportunities** — datasets used by 3+ papers (direct comparison possible)
- **Assumption gaps** — implicit assumptions across papers (potential blind spots)

## Data Flow

```
data/reviews/{paper_id}.json (Level 2)
        ↓ load_extractions()
    list[dict]
        ↓ build_comparison()
    comparison matrices (datasets, baselines, metrics, framework, assumptions)
        ↓ identify_gaps()
    research gaps list
        ↓ render_report("cross_compare.html")
    data/reports/comparisons/comparison_YYYY-MM-DD.html
```

## Design Principles

- Only uses validated Level 1/Level 2 extraction data — never generates new claims
- Gap identification is purely data-driven (counting, coverage analysis)
- Framework overlay uses profile's `framework.layers` for structure
