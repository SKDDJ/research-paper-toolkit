"""Deep paper review: structured extraction from arXiv papers.

Usage:
  python scripts/deep_review.py --paper 2601.05536 --level 1 --profile config/profiles/yiming.yaml
  python scripts/deep_review.py --paper 2601.05536 --level 2 --profile config/profiles/yiming.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml


def _load_dotenv():
    """Load .env file from project root if it exists."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not os.environ.get(key):  # don't override existing env
                os.environ[key] = value

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.arxiv_client import fetch_paper_metadata, fetch_paper_text, fetch_paper_structured, normalize_arxiv_id
from scripts.utils.html_renderer import render_report
from scripts.utils.llm_client import LLMClient
from scripts.utils.schema_validator import validate_extraction


def load_profile(profile_path: str) -> dict:
    with open(profile_path) as f:
        return yaml.safe_load(f)


def build_level1_prompt(metadata: dict, abstract: str, profile: dict) -> tuple[str, str]:
    """Build system + user prompt for Level 1 extraction."""
    anchor_list = "\n".join(
        f"  - {p['id']}: {p['title']}" for p in profile.get("anchor_papers", [])
    )

    system = f"""You are a research paper extraction assistant. Extract structured information from the paper metadata and abstract provided.

CRITICAL RULES:
- Every extracted claim MUST include a "source" field indicating where the information comes from (e.g., "abstract", "metadata").
- If a field cannot be determined from the available text, set the value to null and source to "not_found". NEVER fabricate information.
- Return ONLY valid JSON matching the schema below. No markdown fencing, no explanations.

Research context: {profile.get('research_scope', '')}
Anchor papers the researcher is studying:
{anchor_list}

Output JSON schema (Level 1 — metadata + method summary + experiments overview):
{{
  "paper_id": "arXiv ID",
  "extraction_level": 1,
  "extraction_date": "{date.today().isoformat()}",
  "metadata": {{
    "title": "...",
    "authors": ["..."],
    "affiliations": ["..."],
    "venue": "venue or 'preprint'",
    "year": 2026,
    "arxiv_id": "...",
    "doi": null,
    "code_url": null,
    "one_line_summary": "max 200 chars"
  }},
  "method": {{
    "core_contribution": "2-3 sentences describing the main contribution",
    "core_contribution_source": "abstract or section reference",
    "method_components": [
      {{"name": "...", "description": "...", "source": "abstract"}}
    ],
    "theoretical_results": [
      {{"claim": "...", "type": "theorem|lemma|proposition|bound|guarantee", "source": "..."}}
    ]
  }},
  "experiments": {{
    "datasets": [{{"name": "...", "domain": "...", "size": null, "description": "...", "source": "abstract"}}],
    "baselines": [{{"name": "...", "description": "...", "source": "abstract"}}],
    "metrics": [{{"name": "...", "definition": "...", "source": "abstract"}}],
    "key_results": [{{"description": "...", "metric": "...", "value": null, "comparison": null, "source": "abstract"}}],
    "settings": {{
      "oracle_model": null,
      "proxy_models": [],
      "hardware": null,
      "accuracy_target": null,
      "other": {{}}
    }}
  }}
}}"""

    user = f"""Paper metadata:
- Title: {metadata['title']}
- Authors: {', '.join(metadata['authors'])}
- arXiv ID: {metadata['arxiv_id']}
- Year: {metadata['year']}
- Categories: {', '.join(metadata.get('categories', []))}
- Code URL: {metadata.get('code_url') or 'not found'}
- DOI: {metadata.get('doi') or 'not found'}

Abstract:
{abstract}

Extract structured information following the JSON schema. Remember: every claim needs a source field, use null + "not_found" for missing info."""

    return system, user


def build_level2_prompt(metadata: dict, full_text: str, profile: dict) -> tuple[str, str]:
    """Build system + user prompt for Level 2 deep extraction."""
    anchor_list = "\n".join(
        f"  - {p['id']}: {p['title']}" for p in profile.get("anchor_papers", [])
    )

    framework = profile.get("framework", {})
    framework_name = framework.get("name", "")
    layers = framework.get("layers", [])
    layer_list = "\n".join(f"  {i+1}. {l}" for i, l in enumerate(layers))

    # Build framework mapping schema dynamically from layers
    fw_mapping_schema = {}
    for layer in layers:
        key = layer.lower().replace(" ", "_").replace("/", "_")
        fw_mapping_schema[key] = {"choice": "...", "detail": "...", "source": "section ref"}

    system = f"""You are a senior research paper analyst performing a deep structured review. Extract comprehensive information from the full paper text.

CRITICAL RULES:
- Every extracted claim MUST include a "source" field: section number (e.g., "Section 3.2"), table reference (e.g., "Table 2"), figure reference, or "abstract".
- If information cannot be found, use null with "source": "not_found". NEVER fabricate.
- Be thorough: extract ALL datasets, baselines, metrics, and key results mentioned.
- For the framework mapping, analyze how this paper's method maps to each layer.
- Use **bold** markers around key terms, novel contributions, and important method names in descriptions. Example: "The **task cascade framework** generalizes **model cascades** by varying..."
- Extract important formulas in LaTeX format (key_formulas field).
- Describe key figures and tables (key_figures, key_tables fields).
- Return ONLY valid JSON. No markdown fencing.

Research context: {profile.get('research_scope', '')}

Researcher's framework ({framework_name}):
{layer_list}

Anchor papers for cross-reference:
{anchor_list}

Output JSON schema (Level 2 — full extraction):
{{
  "paper_id": "{metadata['arxiv_id']}",
  "extraction_level": 2,
  "extraction_date": "{date.today().isoformat()}",
  "metadata": {{
    "title": "...", "authors": ["..."], "affiliations": ["..."],
    "venue": "...", "year": 2026, "arxiv_id": "...", "doi": null,
    "code_url": null, "one_line_summary": "max 200 chars"
  }},
  "method": {{
    "core_contribution": "2-3 detailed sentences with **bold** for key terms",
    "core_contribution_source": "section reference",
    "method_components": [
      {{"name": "...", "description": "detailed description with **bold** key terms", "source": "Section X.X"}}
    ],
    "theoretical_results": [
      {{"claim": "...", "type": "theorem|lemma|proposition|bound|guarantee", "source": "Theorem/Section X"}}
    ],
    "key_formulas": [
      {{"formula_id": "Eq. 1", "latex": "LaTeX string", "description": "what this formula represents", "source": "Section X"}}
    ],
    "framework_mapping": {json.dumps(fw_mapping_schema, indent=6)}
  }},
  "experiments": {{
    "datasets": [{{"name": "...", "domain": "...", "size": "...", "description": "...", "source": "Section X / Table X"}}],
    "baselines": [{{"name": "...", "description": "...", "source": "Section X"}}],
    "metrics": [{{"name": "...", "definition": "...", "source": "Section X"}}],
    "key_results": [{{"description": "description with **bold** for key numbers", "metric": "...", "value": "...", "comparison": "vs baseline", "source": "Table X / Figure X"}}],
    "key_figures": [{{"figure_id": "Figure X", "caption": "...", "description": "what this figure shows and why it matters", "source": "Figure X"}}],
    "key_tables": [{{"table_id": "Table X", "caption": "...", "description": "what this table shows and key takeaways", "source": "Table X"}}],
    "settings": {{
      "oracle_model": "...", "proxy_models": ["..."],
      "hardware": "...", "accuracy_target": "...", "other": {{}}
    }}
  }},
  "analysis": {{
    "assumptions": [
      {{"assumption": "...", "explicit": true, "source": "Section X"}}
    ],
    "limitations": [
      {{"limitation": "...", "stated_by_authors": true, "source": "Section X"}}
    ],
    "anchor_cross_references": [
      {{"anchor_paper": "paper_id", "relationship": "shared_dataset|shared_baseline|extends|contradicts|complements", "detail": "...", "source": "Section X"}}
    ]
  }}
}}"""

    return system


def _build_level2_user_prompt(full_text: str, structured: dict | None, layers: list) -> str:
    """Build the user prompt for Level 2, incorporating structured content if available."""
    parts = [f"Full paper text:\n\n{full_text}"]

    if structured:
        # Add extracted tables
        if structured.get("tables"):
            parts.append("\n\n--- EXTRACTED TABLES ---")
            for t in structured["tables"]:
                parts.append(f"\n{t['id']}: {t.get('caption', '')}")
                for row in t.get("rows", [])[:20]:  # Cap rows to avoid bloat
                    parts.append(" | ".join(row))

        # Add extracted formulas
        if structured.get("formulas"):
            parts.append("\n\n--- EXTRACTED FORMULAS ---")
            for f in structured["formulas"]:
                parts.append(f"{f['id']}: ${f['latex']}$")

        # Add extracted figures (descriptions only, not images)
        if structured.get("figures"):
            parts.append("\n\n--- EXTRACTED FIGURES ---")
            for fig in structured["figures"]:
                parts.append(f"{fig['id']}: {fig.get('caption', 'No caption')}")
                if fig.get("url"):
                    parts.append(f"  URL: {fig['url']}")

    parts.append(f"\n\nExtract comprehensive structured information following the JSON schema. Map the method to each of the {len(layers)} framework layers. Cross-reference with anchor papers where applicable. Use **bold** markers for key terms and novel contributions.")

    return "\n".join(parts)


def run_review(arxiv_id: str, level: int, profile: dict) -> dict:
    """Run the extraction pipeline and return the result dict."""
    arxiv_id = normalize_arxiv_id(arxiv_id)
    print(f"Fetching metadata for {arxiv_id}...")
    metadata = fetch_paper_metadata(arxiv_id)

    llm_config = profile.get("llm_config", {})
    provider = llm_config.get("provider", "anthropic")
    client = LLMClient(provider=provider)

    if level == 1:
        model = llm_config.get("level1_model", "claude-haiku-4-5-20251001")
        system, user = build_level1_prompt(metadata, metadata["abstract"], profile)
        print(f"Running Level 1 extraction with {model}...")
        result = client.chat_json(system, user, model=model, max_tokens=4096)
    else:
        model = llm_config.get("level2_model", "claude-opus-4-6")
        print(f"Fetching full paper from ar5iv (structured)...")
        structured = fetch_paper_structured(arxiv_id)
        if structured:
            full_text = structured["text"]
            n_tables = len(structured.get("tables", []))
            n_figs = len(structured.get("figures", []))
            n_formulas = len(structured.get("formulas", []))
            print(f"Got {len(full_text)} chars + {n_tables} tables + {n_figs} figures + {n_formulas} formulas")
        else:
            print("WARNING: ar5iv not available, falling back to plain text...")
            full_text = fetch_paper_text(arxiv_id)
            structured = None

        if not full_text:
            print("WARNING: no full text available, falling back to abstract-only")
            full_text = f"Title: {metadata['title']}\n\nAbstract:\n{metadata['abstract']}"

        # Truncate text if too long
        max_text_len = 80000
        if len(full_text) > max_text_len:
            full_text = full_text[:max_text_len] + "\n\n[... text truncated for length ...]"

        framework_layers = profile.get("framework", {}).get("layers", [])
        system = build_level2_prompt(metadata, "", profile)
        user = _build_level2_user_prompt(full_text, structured, framework_layers)
        print(f"Running Level 2 deep extraction with {model}...")
        result = client.chat_json(system, user, model=model, max_tokens=16384)

        # Inject parsed content from ar5iv into LLM result
        if structured:
            if structured.get("figures"):
                _inject_figure_urls(result, structured["figures"])
            if structured.get("tables"):
                _inject_table_data(result, structured["tables"])

    # Ensure paper_id and level are set
    result["paper_id"] = arxiv_id
    result["extraction_level"] = level
    result["extraction_date"] = date.today().isoformat()

    return result


def _inject_figure_urls(result: dict, parsed_figures: list[dict]) -> None:
    """Match LLM-extracted figure descriptions with parsed figure URLs."""
    key_figures = result.get("experiments", {}).get("key_figures", [])
    if not key_figures:
        return
    # Build a lookup by figure ID
    url_map = {}
    for fig in parsed_figures:
        url_map[fig["id"].lower()] = fig.get("url", "")
        # Also map without "Figure " prefix
        num_match = re.search(r'\d+', fig["id"])
        if num_match:
            url_map[f"figure {num_match.group(0)}"] = fig.get("url", "")
    for kf in key_figures:
        if not kf.get("url"):
            fig_id = kf.get("figure_id", "").lower()
            kf["url"] = url_map.get(fig_id, url_map.get(fig_id.replace("fig.", "figure"), None))


def _inject_table_data(result: dict, parsed_tables: list[dict]) -> None:
    """Inject parsed table HTML/rows from ar5iv into LLM-extracted key_tables."""
    key_tables = result.get("experiments", {}).get("key_tables", [])
    if not key_tables:
        return
    # Build lookup by table ID (case-insensitive)
    table_map = {}
    for t in parsed_tables:
        table_map[t["id"].lower()] = t
        # Also map by number
        num_match = re.search(r'\d+', t["id"])
        if num_match:
            table_map[f"table {num_match.group(0)}"] = t
    for kt in key_tables:
        tbl_id = kt.get("table_id", "").lower()
        parsed = table_map.get(tbl_id, table_map.get(tbl_id.replace("tbl.", "table"), None))
        if parsed:
            kt["rows"] = parsed.get("rows", [])
            kt["html"] = parsed.get("html", "")


def save_results(result: dict, level: int, profile: dict) -> tuple[Path, Path | None]:
    """Save JSON to data/reviews/ and HTML (if level 2) to data/reports/reviews/.

    Returns (json_path, html_path_or_none).
    """
    paper_id = result["paper_id"]
    safe_id = paper_id.replace("/", "_")

    # Save JSON
    json_dir = PROJECT_ROOT / "data" / "reviews"
    json_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_dir / f"{safe_id}.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved JSON: {json_path}")

    # Render HTML for Level 2 (and optionally Level 1)
    html_path = None
    template_data = {
        **result,
        "highlight_authors": profile.get("scoring", {}).get("highlight_authors", []),
        "framework_name": profile.get("framework", {}).get("name", ""),
        "framework_layers": profile.get("framework", {}).get("layers", []),
    }
    html_dir = PROJECT_ROOT / "data" / "reports" / "reviews"
    html_dir.mkdir(parents=True, exist_ok=True)
    html_path = html_dir / f"{safe_id}_L{level}.html"
    render_report("deep_review.html", template_data, html_path)
    print(f"Saved HTML: {html_path}")

    return json_path, html_path


def _review_and_save(arxiv_id: str, level: int, profile: dict) -> bool:
    """Run review + validate + save for a single paper. Returns True on success."""
    try:
        result = run_review(arxiv_id, level, profile)
        errors = validate_extraction(result, level)
        if errors:
            print(f"\nValidation warnings ({len(errors)}):")
            for e in errors:
                print(f"  - {e}")
        else:
            print("\nValidation: OK")
        json_path, html_path = save_results(result, level, profile)
        print(f"  JSON: {json_path}")
        if html_path:
            print(f"  HTML: {html_path}")
        return True
    except Exception as e:
        print(f"\nERROR processing {arxiv_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Deep paper review extraction")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--paper", help="arXiv ID or URL (single paper)")
    group.add_argument("--papers", nargs="+", help="Multiple arXiv IDs for batch extraction")
    group.add_argument("--batch-anchor", action="store_true", help="Extract all anchor papers from profile")
    parser.add_argument("--level", type=int, choices=[1, 2], default=1, help="Extraction level")
    parser.add_argument("--profile", required=True, help="Path to researcher profile YAML")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip papers that already have extraction JSON (default: True)")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    reviews_dir = PROJECT_ROOT / "data" / "reviews"

    # Build list of paper IDs to process
    if args.paper:
        paper_ids = [args.paper]
    elif args.papers:
        paper_ids = args.papers
    elif args.batch_anchor:
        paper_ids = []
        for p in profile.get("anchor_papers", []):
            aid = p.get("arxiv_id")
            if aid:
                paper_ids.append(aid)
            else:
                print(f"WARNING: anchor paper '{p.get('id', '?')}' has no arxiv_id, skipping")
        print(f"Found {len(paper_ids)} anchor papers with arXiv IDs")

    # Filter out already-extracted papers
    if args.skip_existing and len(paper_ids) > 1:
        to_process = []
        for pid in paper_ids:
            from scripts.utils.arxiv_client import normalize_arxiv_id
            safe = normalize_arxiv_id(pid).replace("/", "_")
            if (reviews_dir / f"{safe}.json").exists():
                print(f"Skipping {pid} (already extracted)")
            else:
                to_process.append(pid)
        paper_ids = to_process
        if not paper_ids:
            print("All papers already extracted. Nothing to do.")
            return

    # Process
    total = len(paper_ids)
    success = 0
    for i, pid in enumerate(paper_ids, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{total}] Processing {pid}")
        print(f"{'='*60}")
        if _review_and_save(pid, args.level, profile):
            success += 1

    if total > 1:
        print(f"\n{'='*60}")
        print(f"Batch complete: {success}/{total} papers extracted successfully")
        print(f"{'='*60}")


if __name__ == "__main__":
    _load_dotenv()
    main()
