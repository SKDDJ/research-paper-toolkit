# MineRU Local PDF Parsing — Reference

Local PDF-to-Markdown extraction via [MineRU](https://github.com/opendatalab/MinerU) v3.0.
All processing runs on-device — no data leaves the machine.

## Installation (macOS Apple Silicon)

```bash
# Install MineRU with all backends
uv pip install -U "mineru[all]"

# Download models (pipeline type is sufficient for academic PDFs)
printf "huggingface\npipeline\n" | mineru-models-download
# Or interactively: mineru-models-download

# Verify
mineru --help
```

Requires: macOS 14.0+, Python 3.10-3.13, 16GB+ RAM (32GB recommended).

## How It Integrates

MineRU is the **primary** content source for Level 2 deep review:

```
Level 2 fallback chain:
  1. User --pdf flag          → MineRU parse (or PyMuPDF fallback)
  2. Download arXiv PDF       → MineRU parse     ← PRIMARY for arxiv papers
  3. ar5iv HTML structured    → existing parser   ← fallback
  4. ar5iv plain text                             ← fallback
  5. Abstract only                                ← last resort
```

If MineRU is not installed, the pipeline gracefully falls back to ar5iv HTML.

## CLI Usage (standalone)

```bash
# Parse a single PDF
mineru -p paper.pdf -o ./output/

# Force CPU-only (pipeline backend)
mineru -p paper.pdf -o ./output/ -b pipeline

# Use default backend (hybrid, auto-detects MPS on Mac)
mineru -p paper.pdf -o ./output/
```

## Output Format

MineRU produces a directory with:
- `markdown/*.md` — main content in Markdown (tables as pipe-delimited, formulas as `$$LaTeX$$`, figures as `![](path)`)
- `images/` — extracted figure images
- `content_list.json` — flat content structure
- `layout.pdf` — visual debugging overlay

The toolkit's `pdf_client.py` converts MineRU markdown to the same structured format as ar5iv parsing: `{text, tables, figures, formulas}`.

## Caching

Parsed output is cached at `data/papers/.mineru_cache_<paper_id>/`. Second extraction of the same PDF skips MineRU and reads cached markdown.

## Backends

| Backend | Device | Quality | Speed | macOS Support |
|---------|--------|---------|-------|--------------|
| `pipeline` | CPU | Good | Slower | Full |
| `hybrid-auto-engine` | MPS/CPU | Better | Moderate | Full (default) |
| `vlm-auto-engine` | GPU only | Best | Fast | MPS supported |

Default on macOS: `hybrid-auto-engine` (auto-detects MPS).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MINERU_DEVICE_MODE` | auto | Force device: `cpu`, `mps`, `cuda` |
| `MINERU_MODEL_SOURCE` | huggingface | Model source: `huggingface`, `modelscope`, `local` |
| `MINERU_FORMULA_ENABLE` | true | Toggle formula detection |
| `MINERU_TABLE_ENABLE` | true | Toggle table recognition |

## Troubleshooting

- **MPS out of memory**: Use `MINERU_DEVICE_MODE=cpu mineru -p ...` or `-b pipeline`
- **Models not found**: Run `mineru-models-download` again
- **Slow first run**: Model loading takes 30-60s on first invocation; subsequent runs are faster
- **mineru not found**: Ensure installed in project venv: `uv pip install -U "mineru[all]"`
