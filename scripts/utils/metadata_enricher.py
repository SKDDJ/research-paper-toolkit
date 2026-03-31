"""Metadata enrichment from external APIs (Semantic Scholar, OpenAlex).

Fills in missing venue, DOI, citation count for papers already fetched
from arXiv. Only overwrites null/empty fields — never clobbers existing data.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

_http = httpx.Client(
    timeout=30,
    follow_redirects=True,
    headers={"User-Agent": "research-paper-toolkit/0.1 (mailto:research-toolkit@example.com)"},
)

S2_API = "https://api.semanticscholar.org/graph/v1/paper"
OPENALEX_API = "https://api.openalex.org/works"


def enrich_metadata(arxiv_id: str, existing_meta: dict[str, Any]) -> dict[str, Any]:
    """Enrich paper metadata from external APIs.

    Queries Semantic Scholar and OpenAlex to fill in missing fields.
    Only overwrites fields that are None, empty string, or "preprint".

    Args:
        arxiv_id: Bare arXiv ID (e.g., "2509.02896")
        existing_meta: Current metadata dict from arXiv API

    Returns:
        Updated metadata dict (mutated in place and returned)
    """
    meta = existing_meta
    sources_used = []

    # --- Semantic Scholar ---
    s2_data = _fetch_semantic_scholar(arxiv_id)
    if s2_data:
        sources_used.append("semantic_scholar")

        if _should_update(meta.get("venue"), s2_data.get("venue")):
            meta["venue"] = s2_data["venue"]
        if _should_update(meta.get("doi"), s2_data.get("doi")):
            meta["doi"] = s2_data["doi"]
        if s2_data.get("citation_count") is not None:
            meta["citation_count"] = s2_data["citation_count"]
        if _should_update(meta.get("publication_date"), s2_data.get("publication_date")):
            meta["publication_date"] = s2_data["publication_date"]

        time.sleep(1)  # Rate limit politeness

    # --- OpenAlex ---
    title = meta.get("title", "")
    oalex_data = _fetch_openalex(arxiv_id, title=title)
    if oalex_data:
        sources_used.append("openalex")

        # OpenAlex often has better venue info for recent papers
        if _should_update(meta.get("venue"), oalex_data.get("venue")):
            meta["venue"] = oalex_data["venue"]
        if _should_update(meta.get("doi"), oalex_data.get("doi")):
            meta["doi"] = oalex_data["doi"]

    meta["metadata_sources"] = sources_used
    return meta


def _should_update(current: Any, new: Any) -> bool:
    """Check if a field should be updated with new value."""
    if new is None or new == "":
        return False
    if current is None or current == "" or current == "preprint":
        return True
    return False


def _fetch_semantic_scholar(arxiv_id: str) -> dict[str, Any] | None:
    """Fetch metadata from Semantic Scholar API."""
    url = f"{S2_API}/ARXIV:{arxiv_id}"
    fields = "venue,year,citationCount,externalIds,publicationDate,journal"
    try:
        resp = _http.get(url, params={"fields": fields})
        if resp.status_code == 404:
            print(f"  S2: paper not found for {arxiv_id}")
            return None
        if resp.status_code == 429:
            print("  S2: rate limited, skipping")
            return None
        if resp.status_code != 200:
            print(f"  S2: HTTP {resp.status_code}")
            return None

        data = resp.json()
        result = {}

        # Venue
        venue = data.get("venue")
        if not venue and data.get("journal"):
            venue = data["journal"].get("name")
        if venue:
            result["venue"] = venue

        # DOI from externalIds
        ext_ids = data.get("externalIds", {})
        if ext_ids.get("DOI"):
            result["doi"] = f"https://doi.org/{ext_ids['DOI']}"

        # Citation count
        result["citation_count"] = data.get("citationCount")

        # Publication date
        result["publication_date"] = data.get("publicationDate")

        return result if result else None

    except (httpx.HTTPError, Exception) as e:
        print(f"  S2 error: {e}")
        return None


def _fetch_openalex(arxiv_id: str, title: str | None = None) -> dict[str, Any] | None:
    """Fetch metadata from OpenAlex API using title search."""
    if not title:
        return None

    try:
        # Search by title (most reliable method for arXiv papers)
        resp = _http.get(OPENALEX_API, params={"search": title, "per_page": 1})
        if resp.status_code != 200:
            print(f"  OpenAlex: HTTP {resp.status_code}")
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            print(f"  OpenAlex: no results for '{title[:40]}...'")
            return None

        top = results[0]
        result = {}

        # Host venue (primary publication location)
        primary = top.get("primary_location", {})
        source = primary.get("source", {})
        if source and source.get("display_name"):
            venue_name = source["display_name"]
            # Skip generic preprint servers
            vl = venue_name.lower()
            if not any(skip in vl for skip in ("arxiv", "biorxiv", "medrxiv", "ssrn", "preprint")):
                result["venue"] = venue_name

        # DOI
        doi = top.get("doi")
        if doi:
            result["doi"] = doi

        return result if result else None

    except (httpx.HTTPError, Exception) as e:
        print(f"  OpenAlex error: {e}")
        return None
