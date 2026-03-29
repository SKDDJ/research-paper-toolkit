"""arXiv API client + ar5iv HTML fetcher.

Uses httpx for HTTP requests. No external XML parsing — uses stdlib xml.etree.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

ARXIV_API = "https://export.arxiv.org/api/query"
_MAX_RETRIES = 3
AR5IV_BASE = "https://ar5iv.labs.arxiv.org/html"
ARXIV_ABS = "https://arxiv.org/abs"

_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_http = httpx.Client(timeout=60, follow_redirects=True)


def normalize_arxiv_id(paper_id: str) -> str:
    """Extract bare arXiv ID from URLs or ID strings."""
    # Handle full URLs
    for prefix in ("https://arxiv.org/abs/", "http://arxiv.org/abs/",
                    "https://arxiv.org/pdf/", "http://arxiv.org/pdf/"):
        if paper_id.startswith(prefix):
            paper_id = paper_id[len(prefix):]
            break
    # Strip version suffix and .pdf
    paper_id = re.sub(r"(\.pdf)?(v\d+)?$", "", paper_id)
    return paper_id.strip()


def fetch_paper_metadata(arxiv_id: str) -> dict[str, Any]:
    """Fetch metadata from arXiv API. Returns dict with title, authors, etc."""
    arxiv_id = normalize_arxiv_id(arxiv_id)

    # Try API first, fall back to HTML scraping
    entry = _fetch_api_entry(arxiv_id)
    if entry is None:
        print("  arXiv API unavailable, falling back to HTML scrape...")
        return _scrape_abs_page(arxiv_id)

    title_el = entry.find("atom:title", _NS)
    title = _clean_text(title_el.text) if title_el is not None and title_el.text else ""

    authors = []
    for author_el in entry.findall("atom:author", _NS):
        name_el = author_el.find("atom:name", _NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    summary_el = entry.find("atom:summary", _NS)
    abstract = _clean_text(summary_el.text) if summary_el is not None and summary_el.text else ""

    published_el = entry.find("atom:published", _NS)
    published = published_el.text.strip() if published_el is not None and published_el.text else ""
    year = int(published[:4]) if len(published) >= 4 else 0

    categories = []
    for cat_el in entry.findall("atom:category", _NS):
        term = cat_el.get("term", "")
        if term:
            categories.append(term)

    # Look for code links in comments or links
    comment_el = entry.find("arxiv:comment", _NS)
    comment = comment_el.text.strip() if comment_el is not None and comment_el.text else ""

    code_url = None
    github_match = re.search(r"https?://github\.com/[^\s)]+", comment)
    if github_match:
        code_url = github_match.group(0)
    if not code_url:
        github_match = re.search(r"https?://github\.com/[^\s)]+", abstract)
        if github_match:
            code_url = github_match.group(0)

    # DOI
    doi = None
    for link_el in entry.findall("atom:link", _NS):
        href = link_el.get("href", "")
        if "doi.org" in href:
            doi = href
            break

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "year": year,
        "published": published,
        "categories": categories,
        "code_url": code_url,
        "doi": doi,
        "comment": comment,
    }


def fetch_paper_text(arxiv_id: str) -> str | None:
    """Fetch full paper text from ar5iv HTML version.

    Returns cleaned text content, or None if ar5iv is unavailable.
    """
    arxiv_id = normalize_arxiv_id(arxiv_id)
    url = f"{AR5IV_BASE}/{arxiv_id}"
    try:
        resp = _http.get(url)
        if resp.status_code != 200:
            return None
        return _html_to_text(resp.text)
    except httpx.HTTPError:
        return None


def fetch_paper_structured(arxiv_id: str) -> dict[str, Any] | None:
    """Fetch full paper from ar5iv HTML with structured content.

    Returns dict with: text, tables, figures, formulas.
    Returns None if ar5iv is unavailable.
    """
    arxiv_id = normalize_arxiv_id(arxiv_id)
    url = f"{AR5IV_BASE}/{arxiv_id}"
    try:
        resp = _http.get(url)
        if resp.status_code != 200:
            return None
        return _parse_ar5iv_structured(resp.text, arxiv_id)
    except httpx.HTTPError:
        return None


def _parse_ar5iv_structured(html: str, arxiv_id: str) -> dict[str, Any]:
    """Parse ar5iv HTML into structured content: text, tables, figures, formulas."""

    # Extract tables before stripping HTML
    tables = _extract_tables(html)

    # Extract figures (img URLs + captions)
    figures = _extract_figures(html, arxiv_id)

    # Extract formulas (math elements)
    formulas = _extract_formulas(html)

    # Then get the clean text
    text = _html_to_text(html)

    return {
        "text": text,
        "tables": tables,
        "figures": figures,
        "formulas": formulas,
    }


def _extract_tables(html: str) -> list[dict[str, Any]]:
    """Extract tables from ar5iv HTML, preserving structure."""
    tables = []
    # Match <table> blocks with optional surrounding <figure> for caption
    # ar5iv wraps tables in <figure class="ltx_table">
    table_figures = re.findall(
        r'<figure[^>]*class="[^"]*ltx_table[^"]*"[^>]*>(.*?)</figure>',
        html, re.DOTALL | re.IGNORECASE
    )

    for i, block in enumerate(table_figures):
        # Extract caption
        caption_match = re.search(
            r'<figcaption[^>]*>(.*?)</figcaption>', block, re.DOTALL | re.IGNORECASE
        )
        caption = _clean_text(_strip_tags(caption_match.group(1))) if caption_match else ""

        # Extract table ID (e.g., "Table 1")
        table_id = f"Table {i + 1}"
        id_match = re.search(r'<span[^>]*class="[^"]*ltx_tag[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if id_match:
            tag_text = _clean_text(_strip_tags(id_match.group(1)))
            if tag_text:
                table_id = tag_text.rstrip(":")

        # Extract the raw table HTML (for potential re-rendering)
        table_html_match = re.search(r'(<table[^>]*>.*?</table>)', block, re.DOTALL | re.IGNORECASE)
        table_html = table_html_match.group(1) if table_html_match else ""

        # Parse table rows into structured data
        rows = _parse_table_rows(table_html)

        tables.append({
            "id": table_id,
            "caption": caption,
            "rows": rows,
            "html": table_html,
        })

    # Also catch standalone tables not in <figure>
    if not tables:
        standalone = re.findall(r'(<table[^>]*>.*?</table>)', html, re.DOTALL | re.IGNORECASE)
        for i, table_html in enumerate(standalone):
            rows = _parse_table_rows(table_html)
            if rows and len(rows) > 1:  # Skip trivial layout tables
                tables.append({
                    "id": f"Table {i + 1}",
                    "caption": "",
                    "rows": rows,
                    "html": table_html,
                })

    return tables


def _parse_table_rows(table_html: str) -> list[list[str]]:
    """Parse HTML table into list of rows, each row a list of cell text."""
    rows = []
    for row_match in re.finditer(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE):
        cells = []
        for cell_match in re.finditer(r'<t[hd][^>]*>(.*?)</t[hd]>', row_match.group(1), re.DOTALL | re.IGNORECASE):
            cell_text = _clean_text(_strip_tags(cell_match.group(1)))
            cells.append(cell_text)
        if cells:
            rows.append(cells)
    return rows


def _extract_figures(html: str, arxiv_id: str) -> list[dict[str, Any]]:
    """Extract figures from ar5iv HTML."""
    figures = []
    # ar5iv wraps figures in <figure class="ltx_figure">
    fig_blocks = re.findall(
        r'<figure[^>]*class="[^"]*ltx_figure[^"]*"[^>]*>(.*?)</figure>',
        html, re.DOTALL | re.IGNORECASE
    )

    for i, block in enumerate(fig_blocks):
        # Caption
        caption_match = re.search(
            r'<figcaption[^>]*>(.*?)</figcaption>', block, re.DOTALL | re.IGNORECASE
        )
        caption = _clean_text(_strip_tags(caption_match.group(1))) if caption_match else ""

        # Figure ID
        fig_id = f"Figure {i + 1}"
        id_match = re.search(r'<span[^>]*class="[^"]*ltx_tag[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if id_match:
            tag_text = _clean_text(_strip_tags(id_match.group(1)))
            if tag_text:
                fig_id = tag_text.rstrip(":")

        # Image URL
        img_match = re.search(r'<img[^>]*src="([^"]+)"', block, re.IGNORECASE)
        img_url = ""
        if img_match:
            src = img_match.group(1)
            if src.startswith("/"):
                img_url = f"https://ar5iv.labs.arxiv.org{src}"
            elif src.startswith("http"):
                img_url = src
            else:
                img_url = f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}/{src}"

        figures.append({
            "id": fig_id,
            "caption": caption,
            "url": img_url,
        })

    return figures


def _extract_formulas(html: str) -> list[dict[str, Any]]:
    """Extract key formulas from ar5iv HTML.

    ar5iv renders math as MathML. We extract the alttext attribute
    which contains the LaTeX source.
    """
    formulas = []
    seen = set()

    # ar5iv uses <math> tags with alttext containing LaTeX
    # Look for numbered/labeled equations (in <table class="ltx_equation"> or <math> with id)
    equation_blocks = re.findall(
        r'<(?:table|div)[^>]*class="[^"]*ltx_equation[^"]*"[^>]*>(.*?)</(?:table|div)>',
        html, re.DOTALL | re.IGNORECASE
    )

    for i, block in enumerate(equation_blocks):
        # Get LaTeX from alttext
        alt_match = re.search(r'alttext="([^"]+)"', block)
        latex = alt_match.group(1) if alt_match else ""

        # Get equation number
        tag_match = re.search(r'<span[^>]*class="[^"]*ltx_tag[^"]*"[^>]*>\((\d+)\)</span>', block)
        eq_id = f"Eq. {tag_match.group(1)}" if tag_match else f"Eq. {i + 1}"

        if latex and latex not in seen:
            seen.add(latex)
            formulas.append({
                "id": eq_id,
                "latex": latex,
            })

    return formulas


def _html_to_text(html: str) -> str:
    """Extract readable text from ar5iv HTML. Simple tag stripping."""
    # Remove script/style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove nav/header/footer
    html = re.sub(r"<(nav|header|footer)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Convert <br> and block elements to newlines
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</(p|div|h[1-6]|li|tr)>", "\n", html, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fetch_api_entry(arxiv_id: str):
    """Try arXiv API with retries. Returns XML entry element or None."""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = _http.get(ARXIV_API, params={"id_list": arxiv_id})
            if resp.status_code in (429, 503):
                wait = 5 * (attempt + 1)
                print(f"  arXiv API {resp.status_code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            entry = root.find("atom:entry", _NS)
            if entry is not None:
                return entry
            return None
        except (httpx.HTTPError, ET.ParseError):
            if attempt < _MAX_RETRIES - 1:
                time.sleep(3)
                continue
            return None
    return None


def _scrape_abs_page(arxiv_id: str) -> dict[str, Any]:
    """Fallback: scrape arxiv.org/abs/ page for metadata."""
    url = f"{ARXIV_ABS}/{arxiv_id}"
    resp = _http.get(url)
    resp.raise_for_status()
    html = resp.text

    # Title
    m = re.search(r'<h1 class="title[^"]*">\s*(?:<span[^>]*>Title:</span>)?\s*(.*?)\s*</h1>', html, re.DOTALL)
    title = _clean_text(_strip_tags(m.group(1))) if m else ""

    # Authors
    m = re.search(r'<div class="authors">(.*?)</div>', html, re.DOTALL)
    authors_html = m.group(1) if m else ""
    authors = [a.strip() for a in re.findall(r'>([^<]+)</a>', authors_html) if a.strip()]

    # Abstract
    m = re.search(r'<blockquote class="abstract[^"]*">\s*(?:<span[^>]*>Abstract:</span>)?\s*(.*?)\s*</blockquote>', html, re.DOTALL)
    abstract = _clean_text(_strip_tags(m.group(1))) if m else ""

    # Date / year
    m = re.search(r'\[Submitted on (\d+ \w+ \d{4})', html)
    year = int(m.group(1).split()[-1]) if m else 0

    # Categories
    cats = re.findall(r'<span class="primary-subject">([^<]+)</span>', html)
    categories = [c.strip() for c in cats]

    # Code URL
    code_url = None
    github_match = re.search(r'https?://github\.com/[^\s"<>)]+', html)
    if github_match:
        code_url = github_match.group(0)

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "year": year,
        "published": "",
        "categories": categories,
        "code_url": code_url,
        "doi": None,
        "comment": "",
    }


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _clean_text(text: str) -> str:
    """Collapse whitespace in text."""
    return re.sub(r"\s+", " ", text).strip()
