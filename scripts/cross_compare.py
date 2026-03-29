"""Cross-paper comparison: matrices, framework overlay, and research gap identification.

Usage:
  python scripts/cross_compare.py --anchor-papers --profile config/profiles/yiming.yaml
  python scripts/cross_compare.py --papers 2509.02896 2601.05536 --profile config/profiles/yiming.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.arxiv_client import normalize_arxiv_id
from scripts.utils.html_renderer import render_report


def load_profile(profile_path: str) -> dict:
    with open(profile_path) as f:
        return yaml.safe_load(f)


def load_extractions(paper_ids: list[str], reviews_dir: Path) -> list[dict]:
    """Load Level 2 extraction JSONs for the given paper IDs."""
    extractions = []
    for pid in paper_ids:
        safe = normalize_arxiv_id(pid).replace("/", "_")
        path = reviews_dir / f"{safe}.json"
        if not path.exists():
            print(f"WARNING: No extraction found for {pid}, skipping")
            continue
        with open(path) as f:
            data = json.load(f)
        if data.get("extraction_level", 1) < 2:
            print(f"WARNING: {pid} is only Level {data.get('extraction_level')}, included but may lack fields")
        extractions.append(data)
    return extractions


def _short_title(title: str | None, max_len: int = 40) -> str:
    """Truncate title for display."""
    if not title:
        return ""
    if len(title) <= max_len:
        return title
    return title[:max_len - 3] + "..."


def build_comparison(extractions: list[dict], profile: dict) -> dict:
    """Build all comparison data structures from a list of extraction dicts."""
    papers = []
    for ext in extractions:
        meta = ext.get("metadata", {})
        # Find short ID from profile anchor_papers
        short_id = meta.get("arxiv_id", ext.get("paper_id", ""))
        for ap in profile.get("anchor_papers", []):
            if ap.get("arxiv_id") == meta.get("arxiv_id"):
                short_id = ap.get("id", short_id)
                break
        papers.append({
            "short_id": short_id,
            "arxiv_id": meta.get("arxiv_id", ext.get("paper_id", "")),
            "title": meta.get("title", ""),
            "short_title": _short_title(meta.get("title", "")),
            "authors": meta.get("authors", []),
            "venue": meta.get("venue", ""),
            "year": meta.get("year", 0),
            "one_line_summary": meta.get("one_line_summary", ""),
            "code_url": meta.get("code_url"),
        })

    # Dataset matrix: collect all unique datasets across papers
    all_datasets = {}  # name -> {papers: [short_id], domain, description}
    for ext, paper in zip(extractions, papers):
        for ds in ext.get("experiments", {}).get("datasets", []):
            name = ds.get("name", "").strip()
            if not name:
                continue
            key = name.lower()
            if key not in all_datasets:
                all_datasets[key] = {"name": name, "domain": ds.get("domain", ""), "papers": []}
            all_datasets[key]["papers"].append(paper["short_id"])

    dataset_matrix = sorted(all_datasets.values(), key=lambda d: len(d["papers"]), reverse=True)

    # Baseline matrix
    all_baselines = {}
    for ext, paper in zip(extractions, papers):
        for bl in ext.get("experiments", {}).get("baselines", []):
            name = bl.get("name", "").strip()
            if not name:
                continue
            key = name.lower()
            if key not in all_baselines:
                all_baselines[key] = {"name": name, "papers": []}
            all_baselines[key]["papers"].append(paper["short_id"])

    baseline_matrix = sorted(all_baselines.values(), key=lambda b: len(b["papers"]), reverse=True)

    # Metric matrix
    all_metrics = {}
    for ext, paper in zip(extractions, papers):
        for m in ext.get("experiments", {}).get("metrics", []):
            name = m.get("name", "").strip()
            if not name:
                continue
            key = name.lower()
            if key not in all_metrics:
                all_metrics[key] = {"name": name, "definition": m.get("definition", ""), "papers": []}
            all_metrics[key]["papers"].append(paper["short_id"])

    metric_matrix = sorted(all_metrics.values(), key=lambda m: len(m["papers"]), reverse=True)

    # Framework overlay: papers × layers
    framework = profile.get("framework", {})
    layers = framework.get("layers", [])
    framework_overlay = []
    for layer in layers:
        layer_key = layer.lower().replace(" ", "_").replace("/", "_")
        row = {"layer": layer, "papers": []}
        for ext, paper in zip(extractions, papers):
            mapping = ext.get("method", {}).get("framework_mapping", {})
            entry = mapping.get(layer_key, {})
            row["papers"].append({
                "short_id": paper["short_id"],
                "choice": entry.get("choice", ""),
                "detail": entry.get("detail", ""),
                "has_data": bool(entry.get("choice") or entry.get("detail")),
            })
        # Count how many papers address this layer
        row["coverage"] = sum(1 for p in row["papers"] if p["has_data"])
        framework_overlay.append(row)

    # Assumptions comparison
    all_assumptions = []
    for ext, paper in zip(extractions, papers):
        for a in ext.get("analysis", {}).get("assumptions", []):
            all_assumptions.append({
                "paper": paper["short_id"],
                "assumption": a.get("assumption", ""),
                "explicit": a.get("explicit", True),
                "source": a.get("source", ""),
            })

    # Limitations comparison
    all_limitations = []
    for ext, paper in zip(extractions, papers):
        for l in ext.get("analysis", {}).get("limitations", []):
            all_limitations.append({
                "paper": paper["short_id"],
                "limitation": l.get("limitation", ""),
                "stated_by_authors": l.get("stated_by_authors", True),
                "source": l.get("source", ""),
            })

    # Cross-references
    all_cross_refs = []
    for ext, paper in zip(extractions, papers):
        for ref in ext.get("analysis", {}).get("anchor_cross_references", []):
            all_cross_refs.append({
                "from_paper": paper["short_id"],
                "to_paper": ref.get("anchor_paper", ""),
                "relationship": ref.get("relationship", ""),
                "detail": ref.get("detail", ""),
            })

    return {
        "papers": papers,
        "paper_ids": [p["short_id"] for p in papers],
        "dataset_matrix": dataset_matrix,
        "baseline_matrix": baseline_matrix,
        "metric_matrix": metric_matrix,
        "framework_overlay": framework_overlay,
        "framework_name": framework.get("name", ""),
        "framework_layers": layers,
        "assumptions": all_assumptions,
        "limitations": all_limitations,
        "cross_references": all_cross_refs,
    }


def identify_gaps(comparison: dict) -> list[dict]:
    """Identify research gaps from the comparison data."""
    gaps = []
    paper_count = len(comparison["papers"])

    # Gap type 1: Framework layers with low coverage
    for row in comparison.get("framework_overlay", []):
        coverage = row["coverage"]
        if coverage <= paper_count // 3:  # Less than 1/3 of papers address this layer
            papers_with = [p["short_id"] for p in row["papers"] if p["has_data"]]
            papers_without = [p["short_id"] for p in row["papers"] if not p["has_data"]]
            gaps.append({
                "type": "framework_gap",
                "title": f"Sparse coverage: {row['layer']}",
                "description": f"Only {coverage}/{paper_count} papers address this layer. "
                               f"Papers covering it: {', '.join(papers_with) if papers_with else 'none'}. "
                               f"Not covered by: {', '.join(papers_without)}.",
                "severity": "high" if coverage == 0 else "medium",
            })

    # Gap type 2: Datasets used by only one paper (unique evaluation setting)
    unique_datasets = [d for d in comparison["dataset_matrix"] if len(d["papers"]) == 1]
    if unique_datasets:
        gaps.append({
            "type": "evaluation_gap",
            "title": "Unique evaluation datasets (no cross-paper comparison possible)",
            "description": f"{len(unique_datasets)} datasets are used by only one paper: "
                           + ", ".join(f"{d['name']} ({d['papers'][0]})" for d in unique_datasets[:5]),
            "severity": "low",
        })

    # Gap type 3: Datasets used by many papers (good for comparison)
    shared_datasets = [d for d in comparison["dataset_matrix"] if len(d["papers"]) >= 3]
    if shared_datasets:
        gaps.append({
            "type": "comparison_opportunity",
            "title": "Shared evaluation datasets (cross-comparison possible)",
            "description": f"{len(shared_datasets)} datasets used by 3+ papers: "
                           + ", ".join(f"{d['name']} ({len(d['papers'])} papers)" for d in shared_datasets),
            "severity": "info",
        })

    # Gap type 4: Implicit assumptions (potential research blind spots)
    implicit = [a for a in comparison["assumptions"] if not a["explicit"]]
    if implicit:
        gaps.append({
            "type": "assumption_gap",
            "title": "Implicit assumptions across papers",
            "description": f"{len(implicit)} implicit assumptions found that authors don't explicitly state. "
                           "These represent potential research blind spots worth investigating.",
            "severity": "medium",
        })

    return gaps


def main():
    parser = argparse.ArgumentParser(description="Cross-paper comparison")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--papers", nargs="+", help="arXiv IDs to compare")
    group.add_argument("--anchor-papers", action="store_true", help="Compare all anchor papers from profile")
    parser.add_argument("--profile", required=True, help="Path to researcher profile YAML")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    reviews_dir = PROJECT_ROOT / "data" / "reviews"

    if args.anchor_papers:
        paper_ids = [p["arxiv_id"] for p in profile.get("anchor_papers", []) if p.get("arxiv_id")]
    else:
        paper_ids = args.papers

    print(f"Loading extractions for {len(paper_ids)} papers...")
    extractions = load_extractions(paper_ids, reviews_dir)

    if len(extractions) < 2:
        print(f"ERROR: Need at least 2 extracted papers for comparison, got {len(extractions)}")
        sys.exit(1)

    print(f"Building comparison from {len(extractions)} papers...")
    comparison = build_comparison(extractions, profile)

    print("Identifying research gaps...")
    gaps = identify_gaps(comparison)

    # Render
    template_data = {
        **comparison,
        "gaps": gaps,
        "comparison_date": date.today().isoformat(),
        "total_papers": len(extractions),
    }

    out_dir = PROJECT_ROOT / "data" / "reports" / "comparisons"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"comparison_{date.today().isoformat()}.html"
    render_report("cross_compare.html", template_data, out_path)

    print(f"\nComparison complete!")
    print(f"  Papers compared: {len(extractions)}")
    print(f"  Gaps identified: {len(gaps)}")
    print(f"  HTML report: {out_path}")


if __name__ == "__main__":
    main()
