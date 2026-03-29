# Research Paper Toolkit — Project Build Prompt

## Who You Are Building This For

Yiming is a PhD candidate at UQ (University of Queensland) under Prof. Zhifeng Bao and Dr. Hai Lan. His current research focus is **Semantic Filter Evaluation** — a systematic study of LLM-based semantic filter methods (BARGAIN, ThriftLLM, Nirvana, LOTUS, CSV, Task Cascades, ScaleDoc) targeting VLDB submission. He works with a collaborator RA named Jiayu.

Dr. Lan's requirements for research tools are precisely scoped:
1. **Identifying important and interesting research problems/gaps** — the tool should help researchers discover gaps in their field
2. **Outlining small ideas and mini-experiments for idea testing** — "mini-exp" means the minimal experiment to verify whether one idea is promising, NOT a comprehensive evaluation. It should help researchers quickly check if an idea is worth exploring or should be stopped.
3. Dr. Lan explicitly said: "The tool like automatically experimental running and paper writing we do not need to consider."

## What Already Exists

Yiming has a working **daily paper scanning skill** at `/Users/shiyiming2/Documents/Claude/Scheduled/daily-data-agent-papers/SKILL.md`. It runs as a Claude scheduled task every morning, searches arXiv via web search + arXiv API, filters/scores papers by research relevance, and outputs a Markdown digest to `/Users/shiyiming2/Documents/arxiv_daily_paper/YYYY-MM-DD-data-agent-papers.md`.

This daily scan skill works well for initial screening. What's missing is:
- **Deep structured extraction** from individual papers (datasets, metrics, baselines, scores, method components)
- **Taxonomy management** — collecting important papers into a structured, evolving knowledge base
- **Cross-paper comparison** — comparing anchor papers on shared datasets, identifying setting differences
- **Preference learning** — the system should get smarter about what the researcher cares about over time

## What You Are Building

A **skill directory** called `research-paper-toolkit/` that works with both Claude Code (local execution) and is compatible with OpenClaw deployment in the future. It is NOT a monolithic system, NOT a web app, NOT a library to `pip install`. It is a self-contained directory of skills, scripts, configs, and data.

### Directory Structure (if you have better ideas plz let me know)

```
research-paper-toolkit/
├── SKILL.md                    # Master skill: defines LLM agent behavior for all operations
├── config/
│   ├── schema.json             # Shared: extraction schema for deep review
│   ├── default.yaml            # Shared: default config template  
│   └── profiles/
│       └── yiming.yaml         # Personal: anchor papers, interests, scoring weights
├── scripts/
│   ├── daily_scan.py           # Daily initial screening (existing logic, Python-ized)
│   ├── deep_review.py          # Per-paper deep extraction → JSON + HTML
│   ├── cross_compare.py        # Multi-paper comparison → HTML dashboard
│   ├── taxonomy.py             # Taxonomy CRUD operations
│   ├── preferences.py          # Preference tracking and scoring adjustment
│   └── utils/
│       ├── arxiv_client.py     # arXiv API wrapper
│       ├── llm_client.py       # LLM API abstraction (supports multiple providers)
│       ├── html_renderer.py    # Jinja2-based HTML report generation
│       └── schema_validator.py # JSON schema validation for extraction results
├── templates/
│   ├── deep_review.html        # Single paper deep review (see Design Reference below)
│   ├── daily_digest.html       # Daily digest (enhanced version of current Markdown)
│   ├── comparison.html         # Cross-paper comparison dashboard
│   └── taxonomy_view.html      # Taxonomy browser
├── data/
│   ├── taxonomy.json           # Persistent taxonomy tree
│   ├── preferences.jsonl       # User preference log (bookmark/dismiss/rate actions)
│   ├── reviews/                # Per-paper extraction JSONs
│   │   └── {paper_id}.json
│   └── reports/                # Generated HTML reports
│       ├── daily/
│       ├── reviews/
│       └── comparisons/
├── TODO.md                     # Future enhancements roadmap
└── README.md                   # Setup and usage guide
```

### Architecture Decisions (FIRM — do not deviate)

**1. Two-level extraction model (model cascade):**
- **Level 1 (automatic, low cost):** Python script calls a cheaper LLM API (e.g., Claude Haiku, GPT-4o-mini but we can decide which model to call manually or in the future we can set up a monetary cost budget to dynamically decide which mode l to call (note in the todo list) e.g., we can use rule-based method to filter first then use local embedding model to filter then, use cheaper llm model filter etc. use a cascade method  ) with a strict JSON schema. Extracts metadata and structured fields: authors, venue, year, datasets, metrics, baselines, code links, one-line summary. Triggered automatically for papers scoring ≥ 8 in daily scan. ~2-3k tokens per paper.
- **Level 2 (manual trigger, high quality):** User explicitly requests deep review. Full paper text (PDF or HTML) is provided to a strong model (Claude Opus 4.6, Gemini 3.1 pro etc). Produces: framework mapping, limitation analysis, assumption identification, cross-reference with anchor papers. ~10-15k tokens per paper.
- The script should accept a `--level` flag: `deep_review.py --paper <arxiv_id> --level 1` vs `--level 2`.

**2. Prompt defines behavior, code handles determinism:**
- SKILL.md defines how the LLM agent should reason, what to extract, how to judge relevance
- Python scripts handle: API calls, schema validation, file I/O, HTML rendering, deduplication, preference scoring math
- LLM is NEVER responsible for: file operations, format consistency, deduplication checks, score calculations

**3. Anti-hallucination by design:**
- Every extracted claim must include a `source` field: section number, table number, or "abstract"
- If a field cannot be found in the paper, it must be `null` with `"source": "not_found"` — NEVER fabricated
- Schema validation rejects any extraction result missing required source fields
- Cross-paper comparisons only use data from validated Level 1/Level 2 extractions, never generate new claims

**4. Output format:**
- Daily digest: Markdown (keep existing format, it works)
- Deep review: JSON (structured data) + HTML (human-readable report)
- Cross-comparison: HTML dashboard
- Taxonomy: JSON (data) + HTML (browsable view)

**5. LLM client abstraction:**
- `llm_client.py` must support multiple providers via a simple interface:
  ```python
  class LLMClient:
      def chat(self, messages, model=None, temperature=0, response_format=None) -> str
      def chat_json(self, system_prompt, user_prompt, schema=None) -> dict
  ```
- Provider selection via environment variable `LLM_PROVIDER` (anthropic/openai/custom)
- API keys via `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` `GEMINI_API_KEY`, or `CUSTOM_LLM_BASE_URL` + `CUSTOM_LLM_API_KEY`
- Default Level 1 model and Level 2 model configurable in profile yaml

**6. Skill directory is the unit of deployment:**
- Works with `cd research-paper-toolkit && python scripts/deep_review.py --paper 2601.05536 --level 2`
- Works with Claude Code reading SKILL.md and executing commands
- Future-compatible with OpenClaw (no changes needed to skill structure)

### Extraction Schema (schema.json)

This is the core schema for deep paper review. Every field with `source` must trace back to the paper.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["paper_id", "metadata", "method", "experiments", "analysis"],
  "properties": {
    "paper_id": { "type": "string", "description": "arXiv ID or DOI" },
    "extraction_level": { "enum": [1, 2] },
    "extraction_date": { "type": "string", "format": "date" },
    "metadata": {
      "type": "object",
      "required": ["title", "authors", "venue", "year"],
      "properties": {
        "title": { "type": "string" },
        "authors": { "type": "array", "items": { "type": "string" } },
        "affiliations": { "type": "array", "items": { "type": "string" } },
        "venue": { "type": "string" },
        "year": { "type": "integer" },
        "arxiv_id": { "type": ["string", "null"] },
        "doi": { "type": ["string", "null"] },
        "code_url": { "type": ["string", "null"] },
        "one_line_summary": { "type": "string", "maxLength": 200 }
      }
    },
    "method": {
      "type": "object",
      "properties": {
        "core_contribution": { "type": "string", "description": "2-3 sentences", "source": "required" },
        "method_components": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "description": { "type": "string" },
              "source": { "type": "string" }
            }
          }
        },
        "theoretical_results": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "claim": { "type": "string" },
              "type": { "enum": ["theorem", "lemma", "proposition", "bound", "guarantee"] },
              "source": { "type": "string" }
            }
          }
        },
        "framework_mapping": {
          "type": "object",
          "description": "LEVEL 2 ONLY. Maps to researcher's framework (e.g., Dr. Lan's 7-layer)",
          "additionalProperties": {
            "type": "object",
            "properties": {
              "choice": { "type": "string" },
              "detail": { "type": "string" },
              "source": { "type": "string" }
            }
          }
        }
      }
    },
    "experiments": {
      "type": "object",
      "properties": {
        "datasets": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "source"],
            "properties": {
              "name": { "type": "string" },
              "domain": { "type": "string" },
              "size": { "type": ["string", "null"] },
              "description": { "type": "string" },
              "source": { "type": "string" }
            }
          }
        },
        "baselines": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "source"],
            "properties": {
              "name": { "type": "string" },
              "description": { "type": "string" },
              "source": { "type": "string" }
            }
          }
        },
        "metrics": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "source"],
            "properties": {
              "name": { "type": "string" },
              "definition": { "type": "string" },
              "source": { "type": "string" }
            }
          }
        },
        "key_results": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["description", "source"],
            "properties": {
              "description": { "type": "string" },
              "metric": { "type": "string" },
              "value": { "type": ["string", "number", "null"] },
              "comparison": { "type": ["string", "null"] },
              "source": { "type": "string", "description": "e.g., Table 2, Figure 3" }
            }
          }
        },
        "settings": {
          "type": "object",
          "description": "Experimental configuration details",
          "properties": {
            "oracle_model": { "type": ["string", "null"] },
            "proxy_models": { "type": "array", "items": { "type": "string" } },
            "hardware": { "type": ["string", "null"] },
            "accuracy_target": { "type": ["string", "null"] },
            "other": { "type": "object" }
          }
        }
      }
    },
    "analysis": {
      "type": "object",
      "description": "LEVEL 2 ONLY",
      "properties": {
        "assumptions": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "assumption": { "type": "string" },
              "explicit": { "type": "boolean", "description": "true if stated in paper, false if implicit" },
              "source": { "type": "string" }
            }
          }
        },
        "limitations": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "limitation": { "type": "string" },
              "stated_by_authors": { "type": "boolean" },
              "source": { "type": "string" }
            }
          }
        },
        "anchor_cross_references": {
          "type": "array",
          "description": "Connections to the researcher's anchor papers",
          "items": {
            "type": "object",
            "properties": {
              "anchor_paper": { "type": "string" },
              "relationship": { "enum": ["shared_dataset", "shared_baseline", "extends", "contradicts", "complements"] },
              "detail": { "type": "string" },
              "source": { "type": "string" }
            }
          }
        }
      }
    }
  }
}
```

### Taxonomy Design

The taxonomy is a hierarchical, multi-label structure. A paper can belong to multiple categories. The taxonomy evolves over time as the researcher's understanding deepens.

```json
{
  "version": "1.0",
  "owner": "yiming",
  "last_updated": "2026-03-29T16:00:00Z",
  "research_scope": "Semantic Filter Evaluation for LLM-based Data Processing",
  "anchor_papers": [
    {
      "id": "bargain",
      "title": "Beyond Linear LLM Invocation...",
      "arxiv_id": null,
      "status": "reading",
      "assigned_to": "yiming",
      "notes": "Previously read, re-reading for P0"
    }
  ],
  "categories": {
    "semantic_filter": {
      "description": "Methods for LLM-based semantic filtering with quality guarantees",
      "children": {
        "model_cascade": {
          "description": "Cheap proxy → defer uncertain to oracle",
          "papers": ["bargain", "frugalgpt", "early_abstention"],
          "key_insight": "Cost-accuracy tradeoff via confidence-based routing"
        },
        "clustering_voting": {
          "description": "Cluster data, sample within clusters, vote",
          "papers": ["csv"],
          "key_insight": "Offline clustering reused across queries; sublinear LLM calls"
        },
        "surrogate_operation": {
          "description": "Transform predicate to simpler/related operations",
          "papers": ["task_cascades"],
          "key_insight": "Only method that activates predicate transformation layer"
        },
        "learned_proxy": {
          "description": "Train query-specific lightweight model offline",
          "papers": ["scaledoc"],
          "key_insight": "Offline embedding + online calibration"
        },
        "operator_system": {
          "description": "Declarative semantic operator frameworks",
          "papers": ["lotus", "abacus", "palimpzest"],
          "key_insight": "User specifies intent; system optimizes physical plan"
        }
      }
    },
    "cost_aware_execution": {
      "description": "Optimizing LLM inference cost at system level",
      "children": {},
      "papers": []
    },
    "agent_workflow": {
      "description": "Agent pipeline orchestration and optimization",
      "children": {},
      "papers": []
    }
  },
  "dismissed": [
    { "id": "jackal", "reason": "Text-to-JQL, not relevant to semantic filter" },
    { "id": "ehrsql", "reason": "Text-to-SQL for EHR" }
  ],
  "preferences_summary": {
    "boosted_keywords": ["semantic filter", "cost-aware", "accuracy guarantee", "model cascade"],
    "suppressed_keywords": ["text-to-sql", "table QA", "database tuning"],
    "highlight_authors": ["Zeighami", "Parameswaran", "Fernandez", "Trummer"],
    "total_bookmarks": 0,
    "total_dismissals": 0
  }
}
```

Key design principles for the taxonomy:
- Papers are referenced by short IDs, full metadata lives in `reviews/{paper_id}.json`
- Categories can be nested (children of children) — this allows the tree to deepen as understanding grows
- A paper can appear in multiple categories (multi-label)
- `dismissed` is explicit — the system learns what NOT to recommend
- `preferences_summary` is computed from `preferences.jsonl`, NOT manually edited
- `anchor_papers` has `status` field (reading/read/reproducing/reproduced) for progress tracking

### Researcher Profile (yiming.yaml) (currently I think the yaml is not professional and is too flexible just like openclaw's identity.md/memory.md/todo.md/preference.md is enough)

```yaml 
name: "Yiming Shi"
affiliation: "University of Queensland" # optional, not mandatory
advisors: ["Prof. Zhifeng Bao", "Dr. Hai Lan"] # optional, not mandatory, even we can write a short bio to introduce user here, cause it is not important 

research_scope: "Semantic Filter Evaluation for LLM-based Data Processing"
target_venues: ["SIGMOD", "VLDB", "KDD", "ICDE"]
current_deadline: "VLDB June 2026"

anchor_papers:
  - id: bargain
    title: "Beyond Linear LLM Invocation: An Efficient and Effective Semantic Filter Paradigm"
  - id: thriftllm
    title: "ThriftLLM: On Cost-Effective Selection of Large Language Models for Classification"
  - id: nirvana
    title: "Beyond Relational: Semantic-Aware Multi-Modal Analytics"
  - id: lotus
    title: "Semantic Operators and Their Optimization (LOTUS)"
  - id: csv
    title: "Cut Costs Not Accuracy: LLM-Powered Data Processing with Guarantees"
  - id: task_cascades
    title: "Task Cascades for Efficient Unstructured Data Processing"
  - id: scaledoc
    title: "Scaling LLM-based Predicates over Large Document Collections"

framework:
  name: "Dr. Lan's 7-Layer Semantic Filter Framework"
  layers:
    - "Data Representation Layer"
    - "Candidate Executor / Proxy Layer"
    - "Unit of Decision Layer"
    - "Predicate Transformation Layer"
    - "Calibration / Sampling Layer"
    - "Routing / Action Layer"
    - "Guarantee Layer"

scoring:
  core_keywords: ["semantic filter", "LLM predicate", "accuracy guarantee", "cost-aware", "model cascade", "document processing"]
  exclude_keywords: ["text-to-sql", "table QA", "database tuning", "database internals", "robotics"]
  highlight_authors: ["Zeighami", "Parameswaran", "Shankar", "Fernandez", "Trummer"]
  boost_venues: ["SIGMOD", "VLDB", "PVLDB", "KDD"]

llm_config:
  level1_model: "claude-haiku-4-5-20251001"  # cheap, for metadata extraction
  level2_model: "claude-opus-4-6"             # strong, for deep analysis
  provider: "anthropic"  # or "openai", "custom"

output_dir: "/Users/shiyiming2/Documents/arxiv_daily_paper"
```

### HTML Design Reference

The HTML reports MUST follow this aesthetic (from the approved demo):
- Font: Source Serif 4 for headings, DM Sans for body, JetBrains Mono for code/numbers
- Colors: Warm off-white background (#faf9f6), green accent for positive (#2d5a27), amber for caution (#8b5e00), red for danger (#8b1a1a), blue for info (#1a4f8b)
- Source traceability: Every claim has a gray `§X.X` badge. Missing info has orange `not_found` badge.
- Framework mapping: 7 colored cards in a 2-column grid, each with distinct left border color
- Tables: Clean, minimal borders, monospace for numbers, green bold for best results
- Collapsible sections for detailed method explanations
- NO emojis in section headers. Professional, editorial aesthetic.
- Responsive layout, max-width 900px centered.

Use Jinja2 templates in `templates/` directory. The Python scripts render HTML by loading template + injecting JSON data.

### Workflow (Event-Driven, NOT Fixed Pipeline)

```
DAILY (automated, cron or Claude scheduled task):
  daily_scan.py runs
  → searches arXiv (web search + API, same strategy as existing SKILL.md)
  → filters by profile keywords, deduplicates against existing reviews/
  → applies preference-adjusted scoring (reads preferences.jsonl)
  → outputs daily digest Markdown to output_dir
  → for each paper scoring ≥ 8: auto-triggers deep_review.py --level 1
  → Level 1 results saved to data/reviews/{paper_id}.json

ON-DEMAND (user triggers manually):
  "deep review this paper" → deep_review.py --paper <id> --level 2
  → downloads full text, sends to strong model with full schema
  → produces JSON + HTML report
  
  "bookmark/dismiss this paper" → taxonomy.py bookmark|dismiss --paper <id> [--rating N] [--category X]
  → updates preferences.jsonl and taxonomy.json
  → recalculates preferences_summary for next daily scan

WEEKLY (automated, cron):
  cross_compare.py runs
  → reads all anchor paper Level 2 JSONs
  → generates comparison matrices: shared datasets, metric differences, assumption conflicts
  → outputs HTML dashboard to data/reports/comparisons/
```

### TODO.md (Future Enhancements — Record But Do NOT Implement Now)

```markdown
# Research Paper Toolkit — Future Roadmap

## Phase 2: Interactive Frontend
- [ ] Local localhost server for HTML reports with live interactions
- [ ] Bookmark/dismiss buttons in HTML reports (click → updates preferences.jsonl)
- [ ] Dating-app style swipe interface for daily digest papers
- [ ] Real-time taxonomy tree browser with drag-and-drop reorganization

## Phase 3: Multi-Source Ingestion
- [ ] Google Scholar alerts integration (follow specific researchers' new papers)
- [ ] X.com (Twitter) monitoring for highlight authors
- [ ] WeChat official account articles (公众号)
- [ ] Reddit r/MachineLearning, r/LanguageTechnology
- [ ] Anthropic/OpenAI/Google research blog RSS feeds
- [ ] Conference proceeding feeds (SIGMOD, VLDB, KDD notifications)

## Phase 4: Cloud Deployment + Team Sharing
- [ ] OpenClaw-compatible deployment
- [ ] Shared taxonomy with team merge/sync
- [ ] Migrate from JSON to SQLite for multi-user access
- [ ] Team dashboard showing all members' research progress

## Phase 5: Intelligent Features
- [ ] Preference-based recommendation model (beyond keyword TF-IDF)
- [ ] Embedding-based paper similarity for taxonomy suggestions
- [ ] Auto-generated research gap reports from cross-comparison data
- [ ] Mini-experiment designer (idea → minimal testable prototype)
```

### Implementation Priority

Build in this order. Each step should be independently testable:

1. **`config/` + `scripts/utils/`** — schema.json, llm_client.py, schema_validator.py, html_renderer.py. Foundation layer.
2. **`scripts/deep_review.py` + `templates/deep_review.html`** — The core value prop. Must work standalone: `python scripts/deep_review.py --paper 2601.05536 --level 1 --profile config/profiles/yiming.yaml`
3. **`scripts/taxonomy.py`** — CRUD for taxonomy.json. `taxonomy.py init`, `taxonomy.py bookmark`, `taxonomy.py dismiss`, `taxonomy.py show`.
4. **`scripts/daily_scan.py`** — Port existing SKILL.md logic to Python. Must produce same quality output. Add preference-adjusted scoring.
5. **`scripts/preferences.py`** — Read preferences.jsonl, compute keyword boosts/suppressions, expose as scoring function for daily_scan.
6. **`scripts/cross_compare.py` + `templates/comparison.html`** — Reads all anchor paper JSONs, generates comparison dashboard.

### Testing Criteria

After building, test with:
1. `python scripts/deep_review.py --paper 2601.05536 --level 1 --profile config/profiles/yiming.yaml` — should produce a valid JSON + simple HTML for Task Cascades
2. `python scripts/deep_review.py --paper 2601.05536 --level 2 --profile config/profiles/yiming.yaml` — should produce full HTML report matching the demo aesthetic
3. `python scripts/taxonomy.py init --profile config/profiles/yiming.yaml` — should create taxonomy.json from profile anchor papers
4. `python scripts/taxonomy.py bookmark --paper task_cascades --rating 5 --category semantic_filter/surrogate_operation` — should update both files
5. All generated JSONs must pass `schema_validator.py` — no hallucinated fields, all sources present

### Critical Constraints

- **NO hallucination tolerance.** Every extracted fact must have a source trace. `null` with `"source": "not_found"` is always preferred over fabrication.
- **NO over-engineering.** This is a tool for researchers, not a product. If something can be a 20-line Python function, don't make it a class hierarchy.
- **NO external dependencies beyond stdlib + httpx + jinja2.** Keep `pip install` minimal. Use `httpx` for API calls, `jinja2` for HTML templating. Everything else from Python stdlib.
- **Profile-driven personalization.** Everything that differs between researchers (anchor papers, keywords, framework layers, model preferences) lives in the YAML profile, not hardcoded.
- **Incremental delivery.** Each script must work standalone. Don't build a monolith that only works when everything is connected.