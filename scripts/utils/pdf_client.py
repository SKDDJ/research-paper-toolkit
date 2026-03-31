"""PDF download and parsing via MineRU v3.0 CLI.

Downloads arXiv PDFs and parses them into structured content (text, tables,
figures, formulas) matching the same dict shape as
arxiv_client._parse_ar5iv_structured().

MineRU v3.0 is invoked via CLI subprocess (`mineru -p ... -o ...`),
NOT the old v1.x Python API (UNIPipe).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx

from scripts.utils.arxiv_client import normalize_arxiv_id

_http = httpx.Client(timeout=120, follow_redirects=True)

ARXIV_PDF_BASE = "https://arxiv.org/pdf"
DEFAULT_PAPERS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "papers"

# Timeout for MineRU CLI (seconds).
# MineRU v3.0 on M1 Pro pipeline backend: ~30s model loading + 3-10 min parsing
# for a 20-page academic PDF. 30 minutes is generous but safe.
_MINERU_TIMEOUT = 1800
_MINERU_MAX_RETRIES = 2  # Total attempts (1 initial + 1 retry)


def is_pdf_parsing_available() -> bool:
    """Check if MineRU CLI (`mineru`) is on PATH."""
    return shutil.which("mineru") is not None


def download_arxiv_pdf(arxiv_id: str, papers_dir: Path | None = None) -> Path | None:
    """Download PDF from arXiv. Returns cached path if already downloaded.

    Returns None if download fails.
    """
    arxiv_id = normalize_arxiv_id(arxiv_id)
    safe_id = arxiv_id.replace("/", "_")
    dest_dir = papers_dir or DEFAULT_PAPERS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{safe_id}.pdf"

    # Use cache if exists and reasonable size
    if dest.exists() and dest.stat().st_size > 10_000:
        print(f"  PDF cached: {dest}")
        return dest

    url = f"{ARXIV_PDF_BASE}/{arxiv_id}"
    print(f"  Downloading PDF from {url}...")
    try:
        resp = _http.get(url)
        if resp.status_code != 200:
            print(f"  PDF download failed: HTTP {resp.status_code}")
            return None

        # Verify it's actually a PDF
        if not resp.content[:5].startswith(b"%PDF"):
            print("  WARNING: Downloaded file is not a valid PDF")
            return None

        dest.write_bytes(resp.content)
        print(f"  PDF saved: {dest} ({len(resp.content) / 1024:.0f} KB)")
        return dest
    except httpx.HTTPError as e:
        print(f"  PDF download error: {e}")
        return None


def parse_pdf(pdf_path: Path, *, use_cache: bool = True) -> dict[str, Any] | None:
    """Parse PDF using MineRU CLI. Returns structured dict or None on failure.

    Output shape matches arxiv_client._parse_ar5iv_structured():
    {text: str, tables: list[dict], figures: list[dict], formulas: list[dict]}

    Results are cached in a sibling directory to avoid re-parsing.
    """
    if not is_pdf_parsing_available():
        print("  MineRU not installed, cannot parse PDF")
        return None

    # Check cache first
    cache_dir = _get_cache_path(pdf_path)
    if use_cache and cache_dir.exists():
        md_files = list(cache_dir.glob("**/*.md"))
        if md_files:
            md_file = max(md_files, key=lambda f: f.stat().st_size)
            print(f"  Using cached MineRU output: {md_file}")
            md_content = md_file.read_text(encoding="utf-8", errors="replace")
            if len(md_content) > 500:
                return _mineru_md_to_structured(md_content, cache_dir)

    for attempt in range(1, _MINERU_MAX_RETRIES + 1):
        try:
            return _mineru_parse(pdf_path)
        except Exception as e:
            print(f"  MineRU attempt {attempt}/{_MINERU_MAX_RETRIES} failed: {e}")
            if attempt < _MINERU_MAX_RETRIES:
                print(f"  Retrying...")
    return None


def _get_cache_path(pdf_path: Path) -> Path:
    """Cache directory for MineRU output alongside the PDF."""
    return pdf_path.parent / f".mineru_cache_{pdf_path.stem}"


def parse_pdf_simple(pdf_path: Path) -> str | None:
    """Simple text extraction from PDF without MineRU.

    Uses PyMuPDF (fitz) if available, otherwise returns None.
    Useful as a lighter fallback when MineRU is too heavy.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        text = "\n\n".join(text_parts)
        return text if len(text) > 500 else None
    except ImportError:
        return None
    except Exception as e:
        print(f"  PyMuPDF extraction failed: {e}")
        return None


def _mineru_parse(pdf_path: Path) -> dict[str, Any]:
    """Parse PDF via MineRU v3.0 CLI subprocess.

    Runs `mineru -p <pdf> -o <output_dir>` and reads the generated markdown.
    Output is cached for subsequent calls.
    """
    cache_dir = _get_cache_path(pdf_path)
    # Use a temp dir for parsing, then move to cache on success
    work_dir = pdf_path.parent / f".mineru_tmp_{pdf_path.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        cmd = ["mineru", "-p", str(pdf_path), "-o", str(work_dir)]
        print(f"  Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_MINERU_TIMEOUT,
        )

        if result.returncode != 0:
            stderr_snippet = result.stderr[:500] if result.stderr else "(no stderr)"
            raise RuntimeError(f"mineru exit code {result.returncode}: {stderr_snippet}")

        # MineRU v3.0 output structure: work_dir/<pdf_stem>/markdown/<pdf_stem>.md
        # or sometimes work_dir/markdown/<pdf_stem>.md — search recursively
        md_files = list(work_dir.glob("**/*.md"))
        if not md_files:
            raise RuntimeError(f"No markdown output found in {work_dir}")

        # Pick the largest .md file (main content, not README etc.)
        md_file = max(md_files, key=lambda f: f.stat().st_size)
        md_content = md_file.read_text(encoding="utf-8", errors="replace")

        if len(md_content) < 500:
            raise RuntimeError(f"MineRU output too short ({len(md_content)} chars)")

        print(f"  MineRU output: {len(md_content)} chars from {md_file.name}")

        # Cache the output (move work_dir → cache_dir)
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        work_dir.rename(cache_dir)

        return _mineru_md_to_structured(md_content, cache_dir)

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"MineRU timed out after {_MINERU_TIMEOUT}s")
    finally:
        # Clean up work dir if it still exists (not renamed to cache)
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


def _mineru_md_to_structured(md_content: str, output_dir: Path) -> dict[str, Any]:
    """Convert MineRU markdown output to the structured dict format.

    Parses markdown tables, LaTeX blocks, and image references into
    the same shape as arxiv_client structured content.
    """
    tables = _extract_md_tables(md_content)
    formulas = _extract_md_formulas(md_content)
    figures = _extract_md_figures(md_content, output_dir)

    # Clean text: remove table blocks, formula blocks, image references
    text = md_content
    # Remove HTML tables
    text = re.sub(r'<table>.*?</table>', '', text, flags=re.DOTALL)
    # Remove markdown table blocks
    text = re.sub(r'\|[^\n]+\|\n(?:\|[-:| ]+\|\n)?(?:\|[^\n]+\|\n)*', '', text)
    # Remove display math
    text = re.sub(r'\$\$[^$]+\$\$', '', text, flags=re.DOTALL)
    # Remove image refs
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
    # Collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    return {
        "text": text,
        "tables": tables,
        "figures": figures,
        "formulas": formulas,
    }


def _extract_md_tables(md: str) -> list[dict[str, Any]]:
    """Extract tables from MineRU markdown output.

    MineRU v3.0 outputs tables in HTML <table> format or pipe-delimited markdown.
    Handles both.
    """
    tables = []
    table_idx = 0

    # 1) HTML tables (<table>...</table>) — MineRU v3.0 primary format
    for m in re.finditer(r'(<table>.*?</table>)', md, re.DOTALL):
        html_block = m.group(1)
        rows = []
        for row_m in re.finditer(r'<tr>(.*?)</tr>', html_block, re.DOTALL):
            cells = re.findall(r'<t[dh]>(.*?)</t[dh]>', row_m.group(1), re.DOTALL)
            cells = [c.strip() for c in cells]
            if cells:
                rows.append(cells)
        if rows:
            table_idx += 1
            tables.append({
                "id": f"Table {table_idx}",
                "caption": "",
                "rows": rows,
                "html": html_block,
            })

    # 2) Pipe-delimited markdown tables (fallback)
    pattern = r'(\|[^\n]+\|\n\|[-:| ]+\|\n(?:\|[^\n]+\|\n)*)'
    for m in re.finditer(pattern, md):
        block = m.group(1)
        lines = [l.strip() for l in block.strip().split('\n') if l.strip()]
        rows = []
        for j, line in enumerate(lines):
            if j == 1 and re.match(r'^\|[-:| ]+\|$', line):
                continue  # Skip separator line
            cells = [c.strip() for c in line.strip('|').split('|')]
            rows.append(cells)
        if rows:
            table_idx += 1
            tables.append({
                "id": f"Table {table_idx}",
                "caption": "",
                "rows": rows,
                "html": "",
            })

    return tables


def _extract_md_formulas(md: str) -> list[dict[str, Any]]:
    """Extract display math ($$...$$) blocks."""
    formulas = []
    seen = set()
    for i, m in enumerate(re.finditer(r'\$\$\s*(.+?)\s*\$\$', md, re.DOTALL)):
        latex = m.group(1).strip()
        if latex and latex not in seen:
            seen.add(latex)
            formulas.append({
                "id": f"Eq. {i + 1}",
                "latex": latex,
            })
    return formulas


def _extract_md_figures(md: str, output_dir: Path) -> list[dict[str, Any]]:
    """Extract image references from markdown."""
    figures = []
    for i, m in enumerate(re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', md)):
        caption = m.group(1)
        img_path = m.group(2)
        # Resolve relative paths
        full_path = (output_dir / img_path) if not img_path.startswith(('http', '/')) else None
        figures.append({
            "id": f"Figure {i + 1}",
            "caption": caption,
            "url": str(full_path) if full_path and full_path.exists() else img_path,
        })
    return figures
