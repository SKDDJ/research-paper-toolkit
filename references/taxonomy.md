# Taxonomy Management — Reference (Planned)

Hierarchical, multi-label paper organization that evolves with the researcher's understanding.

## Planned CLI

```bash
# Initialize taxonomy from profile anchor papers
uv run python scripts/taxonomy.py init --profile config/profiles/<name>.yaml

# Bookmark a paper into a taxonomy category
uv run python scripts/taxonomy.py bookmark --paper <id> --rating <1-5> --category <path>

# Dismiss a paper (teaches the system what NOT to recommend)
uv run python scripts/taxonomy.py dismiss --paper <id> --reason "not relevant because..."

# Display taxonomy tree
uv run python scripts/taxonomy.py show
```

## Design Principles

- Papers referenced by short IDs; full metadata lives in `data/reviews/{paper_id}.json`
- Categories can nest arbitrarily (children of children) — tree deepens as understanding grows
- A paper can appear in multiple categories (multi-label)
- `dismissed` list is explicit — the system learns what NOT to recommend
- `preferences_summary` is computed from `data/preferences.jsonl`, never manually edited
- Anchor papers have `status` field: reading → read → reproducing → reproduced

## Data Files

- `data/taxonomy.json` — taxonomy tree structure
- `data/preferences.jsonl` — user action log (bookmark, dismiss, rate)

## Status: Not yet implemented. Planned for Phase 1.5 (Priority 3).
