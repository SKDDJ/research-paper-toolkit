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


_PLACEHOLDER_PHRASES = [
    "unable to determine",
    "paper content not available",
    "conversion failure",
    "not available due to",
    "paper text unavailable",
    "could not be extracted",
    "state-of-the-art semantic filter approaches",  # generic CSV placeholder
    "real-world datasets",  # generic CSV placeholder
]


def _is_placeholder(text: str) -> bool:
    """Check if text is a placeholder/filler rather than real extracted content."""
    if not text or not text.strip():
        return True
    lower = text.strip().lower()
    return any(phrase in lower for phrase in _PLACEHOLDER_PHRASES)


def _short_title(title: str | None, max_len: int = 40) -> str:
    """Truncate title for display."""
    if not title:
        return ""
    if len(title) <= max_len:
        return title
    return title[:max_len - 3] + "..."


def assess_extraction_quality(ext: dict) -> dict:
    """Score extraction quality on a 0-1 scale.

    Returns dict with: score (float), grade (str), issues (list[str]), content_source (str).
    """
    score = 1.0
    issues = []
    meta = ext.get("metadata", {})
    method = ext.get("method", {})
    experiments = ext.get("experiments", {})

    # Metadata completeness
    if not meta.get("title"):
        score -= 0.2
        issues.append("Missing title")
    if not meta.get("authors"):
        score -= 0.1
        issues.append("Missing authors")

    # Core contribution
    cc = method.get("core_contribution") or ""
    if not cc or _is_placeholder(cc):
        score -= 0.2
        issues.append("Missing or placeholder core contribution")

    # Experiments
    datasets = experiments.get("datasets", [])
    real_datasets = [d for d in datasets if not _is_placeholder(d.get("name", ""))]
    if not real_datasets:
        score -= 0.2
        issues.append("No real datasets extracted")

    baselines = experiments.get("baselines", [])
    real_baselines = [b for b in baselines if not _is_placeholder(b.get("name", ""))]
    if not real_baselines:
        score -= 0.15
        issues.append("No real baselines extracted")

    metrics = experiments.get("metrics", [])
    if not metrics:
        score -= 0.1
        issues.append("No metrics extracted")

    # Framework mapping quality
    fm = method.get("framework_mapping", {})
    placeholder_layers = 0
    for key, entry in fm.items():
        if isinstance(entry, dict):
            choice = entry.get("choice", "") or ""
            detail = entry.get("detail", "") or ""
            if _is_placeholder(choice) and _is_placeholder(detail):
                placeholder_layers += 1
    if placeholder_layers > 0:
        deduction = min(0.15, placeholder_layers * 0.03)
        score -= deduction
        if placeholder_layers >= 5:
            issues.append(f"Framework mapping mostly placeholder ({placeholder_layers} layers)")

    # Content source
    content_source = ext.get("content_source", "unknown")
    if content_source == "abstract_only":
        score -= 0.1
        issues.append("Extracted from abstract only")

    score = max(0.0, score)

    # Grade
    if score >= 0.6:
        grade = "good"
    elif score >= 0.3:
        grade = "partial"
    else:
        grade = "unusable"

    return {
        "score": round(score, 2),
        "grade": grade,
        "issues": issues,
        "content_source": content_source,
    }


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
        quality = ext.get("_quality", {})
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
            "quality_grade": quality.get("grade", ""),
            "quality_score": quality.get("score", 0),
        })

    # Dataset matrix: collect all unique datasets across papers
    all_datasets = {}  # name -> {papers: [short_id], domain, description}
    for ext, paper in zip(extractions, papers):
        for ds in ext.get("experiments", {}).get("datasets", []):
            name = ds.get("name", "").strip()
            if not name or _is_placeholder(name):
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
            if not name or _is_placeholder(name):
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
            if not name or _is_placeholder(name):
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
            choice = entry.get("choice", "") or ""
            detail = entry.get("detail", "") or ""
            has_real_data = (
                (bool(choice) and not _is_placeholder(choice)) or
                (bool(detail) and not _is_placeholder(detail))
            )
            row["papers"].append({
                "short_id": paper["short_id"],
                "choice": choice,
                "detail": detail,
                "has_data": has_real_data,
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


def identify_gaps(comparison: dict, quality_info: dict | None = None) -> list[dict]:
    """Identify research gaps from the comparison data."""
    gaps = []
    paper_count = len(comparison["papers"])
    # Use usable paper count for thresholds (exclude unusable extractions)
    if quality_info:
        usable_count = sum(1 for q in quality_info.values() if q.get("grade") != "unusable")
    else:
        usable_count = paper_count

    # Gap type 1: Framework layers with low coverage
    for row in comparison.get("framework_overlay", []):
        coverage = row["coverage"]
        if coverage <= usable_count // 3:  # Less than 1/3 of usable papers address this layer
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

    # Assess extraction quality
    print("Assessing extraction quality...")
    quality_info = {}
    quality_warnings = []
    for ext in extractions:
        pid = ext.get("paper_id", "")
        q = assess_extraction_quality(ext)
        quality_info[pid] = q
        # Find short_id from profile
        short_id = pid
        for ap in profile.get("anchor_papers", []):
            if ap.get("arxiv_id") == pid:
                short_id = ap.get("id", pid)
                break
        if q["grade"] != "good":
            quality_warnings.append({
                "paper": short_id,
                "arxiv_id": pid,
                "grade": q["grade"],
                "score": q["score"],
                "issues": q["issues"],
                "content_source": q["content_source"],
            })
            print(f"  {short_id}: {q['grade']} (score={q['score']}, issues={q['issues']})")

    # Inject quality grades into comparison data for template
    for ext in extractions:
        ext["_quality"] = quality_info.get(ext.get("paper_id", ""), {})

    print(f"Building comparison from {len(extractions)} papers...")
    comparison = build_comparison(extractions, profile)

    print("Identifying research gaps...")
    gaps = identify_gaps(comparison, quality_info)

    # Render
    usable = sum(1 for q in quality_info.values() if q["grade"] != "unusable")
    template_data = {
        **comparison,
        "gaps": gaps,
        "quality_warnings": quality_warnings,
        "comparison_date": date.today().isoformat(),
        "total_papers": len(extractions),
        "usable_papers": usable,
    }

    out_dir = PROJECT_ROOT / "data" / "reports" / "comparisons"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"comparison_{date.today().isoformat()}.html"
    render_report("cross_compare.html", template_data, out_path)

    print(f"\nComparison complete!")
    print(f"  Papers compared: {len(extractions)} ({usable} usable)")
    print(f"  Quality warnings: {len(quality_warnings)}")
    print(f"  Gaps identified: {len(gaps)}")
    print(f"  HTML report: {out_path}")


if __name__ == "__main__":
    main()
