# Profile System — Reference

All researcher-specific configuration lives in YAML profiles at `config/profiles/<name>.yaml`. Scripts read personalization from profiles — nothing is hardcoded.

## Creating a New Profile

Copy the default template and customize:

```bash
cp config/default.yaml config/profiles/<name>.yaml
```

## Profile Fields

```yaml
# Identity (optional, for display only)
name: "Researcher Name"
affiliation: "University"
advisors: ["Prof. X", "Dr. Y"]

# Research context (drives prompt construction)
research_scope: "Description of research focus"
target_venues: ["SIGMOD", "VLDB"]
current_deadline: "VLDB June 2026"

# Anchor papers (used for cross-referencing in Level 2 extraction)
anchor_papers:
  - id: short_name
    title: "Full paper title"

# Analytical framework (optional — enables framework mapping in Level 2)
framework:
  name: "Framework Name"
  layers:
    - "Layer 1 Name"
    - "Layer 2 Name"

# Scoring criteria (for daily scan filtering)
scoring:
  core_keywords: ["keyword1", "keyword2"]
  exclude_keywords: ["irrelevant_topic"]
  highlight_authors: ["LastName1", "LastName2"]
  boost_venues: ["SIGMOD", "VLDB"]

# LLM configuration
llm_config:
  provider: "anthropic"          # anthropic | openai | gemini | runway | custom
  level1_model: "claude-haiku-4-5-20251001"
  level2_model: "claude-opus-4-6"

# Output (for daily scan digest)
output_dir: "/path/to/daily/output"
```

## How Profiles Drive Behavior

| Profile Field | Used By | Effect |
|---------------|---------|--------|
| `research_scope` | Level 1 & 2 prompts | Contextualizes extraction |
| `anchor_papers` | Level 2 prompt | Cross-references with known papers |
| `framework.layers` | Level 2 prompt + HTML | Framework mapping section in report |
| `scoring.*` | Daily scan (planned) | Paper relevance scoring |
| `llm_config.provider` | LLM client | Selects API endpoint |
| `llm_config.level1_model` | Level 1 extraction | Model for cheap extraction |
| `llm_config.level2_model` | Level 2 extraction | Model for deep extraction |
| `highlight_authors` | HTML template | Bolds highlighted author names |

## Supported LLM Providers

| Provider | Env Var | Notes |
|----------|---------|-------|
| `anthropic` | `ANTHROPIC_API_KEY` | Direct Anthropic API |
| `openai` | `OPENAI_API_KEY` | OpenAI-compatible |
| `gemini` | `GEMINI_API_KEY` | Google Gemini |
| `runway` | `RUNWAY_CLAUDE_TOKEN` | Bedrock proxy (no model field) |
| `custom` | `CUSTOM_LLM_BASE_URL` + `CUSTOM_LLM_API_KEY` | Any OpenAI-compatible endpoint |
