# Research Paper Toolkit

A skill-directory toolkit for structured paper extraction, taxonomy management, and cross-paper comparison. Designed for integration with Claude Code and OpenClaw.

## Quick Start

```bash
# Install dependencies
uv sync

# Run a Level 1 (quick) review
uv run python scripts/deep_review.py --paper 2601.05536 --level 1 --profile config/profiles/yiming.yaml

# Run a Level 2 (deep) review with framework mapping, formulas, figures
uv run python scripts/deep_review.py --paper 2601.05536 --level 2 --profile config/profiles/yiming.yaml
```

## Architecture

**Two-level extraction model:**
- **Level 1**: Cheap model, abstract-only, metadata + method summary (~2-3k tokens)
- **Level 2**: Strong model, full paper text, framework mapping + analysis + formulas + figures (~10-15k tokens)

**Paper content source:** ar5iv HTML (tables, figures, formulas preserved). MineRU PDF parsing planned for Phase 2.

**Output:** JSON (structured data in `data/reviews/`) + HTML reports (in `data/reports/reviews/`)

## Project Structure

```
SKILL.md                     # Lean skill router (Claude Code integration)
references/                  # Detailed reference docs (loaded on demand)
  deep-review.md             # Deep review CLI, schema, output format
  profile-system.md          # Profile field reference, new researcher setup
  taxonomy.md                # Taxonomy management (planned)
  cross-compare.md           # Cross-paper comparison (planned)
config/                      # Schema and researcher profiles
  schema.json                # Extraction schema
  profiles/yiming.yaml       # Researcher profile (anchor papers, framework, scoring)
scripts/
  deep_review.py             # Main extraction CLI
  utils/
    llm_client.py            # Multi-provider LLM client (Anthropic, OpenAI, Gemini, Runway)
    arxiv_client.py          # arXiv API + ar5iv structured parser
    schema_validator.py      # Lightweight extraction validation
    html_renderer.py         # Jinja2 renderer with bold post-processing
templates/
  deep_review.html           # HTML report template (MathJax, editorial aesthetic)
data/
  reviews/                   # Per-paper extraction JSONs
  reports/                   # Generated HTML reports
```

## Skill Architecture

This toolkit follows Claude Code skill best practices with **progressive disclosure**:

1. **SKILL.md** (~50 lines) — always in context, lean router with trigger phrases
2. **references/** — loaded on demand when Claude needs detail for a specific capability
3. **scripts/** — Python CLI tools executed by Claude

All researcher-specific configuration lives in `config/profiles/<name>.yaml`. See `references/profile-system.md` for the full field reference.

## Configuration

Set your LLM provider credentials in `.env`:

```bash
# For Runway Bedrock proxy (Claude Opus 4.6)
RUNWAY_CLAUDE_TOKEN=your_token_here

# For direct Anthropic API
ANTHROPIC_API_KEY=sk-ant-...

# For OpenAI
OPENAI_API_KEY=sk-...
```

Configure the provider in your profile YAML (`llm_config.provider`).

## Dependencies

Minimal: `httpx`, `jinja2`, `pyyaml`. Managed via `uv`.
