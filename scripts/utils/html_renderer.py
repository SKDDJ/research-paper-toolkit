"""Jinja2-based HTML report renderer with markdown post-processing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

# Templates dir is at project_root/templates/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"


def _bold_filter(text: str) -> Markup:
    """Convert **bold** markers in text to <strong> tags."""
    if not isinstance(text, str):
        return text
    converted = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    return Markup(converted)


def _latex_inline_filter(text: str) -> Markup:
    """Convert $...$ inline math to MathJax-compatible spans."""
    if not isinstance(text, str):
        return text
    # Avoid matching $$ (display math)
    converted = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', r'\\(\1\\)', text)
    return Markup(converted)


def get_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Register custom filters
    env.filters["bold"] = _bold_filter
    env.filters["latex_inline"] = _latex_inline_filter
    return env


def render_report(template_name: str, data: dict[str, Any], output_path: str | Path) -> Path:
    """Render a Jinja2 template with data and write to output_path.

    Pre-processes text fields to convert **bold** markers to <strong> tags.
    Returns the output path as a Path object.
    """
    # Pre-process: convert **bold** in string values throughout the data
    data = _process_bold_markers(data)

    env = get_env()
    template = env.get_template(template_name)
    html = template.render(**data)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def _process_bold_markers(obj: Any) -> Any:
    """Recursively convert **bold** markers in all string values to <strong> tags."""
    if isinstance(obj, str):
        return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', obj)
    elif isinstance(obj, dict):
        return {k: _process_bold_markers(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_process_bold_markers(item) for item in obj]
    return obj
