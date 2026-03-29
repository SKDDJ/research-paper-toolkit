"""Lightweight schema validator for paper extraction results.

Checks required fields, source traceability, and enum values
without depending on the jsonschema package.
"""

from __future__ import annotations

from typing import Any


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s): {'; '.join(errors[:5])}")


def validate_extraction(data: dict, level: int = 1) -> list[str]:
    """Validate a paper extraction dict. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Top-level required
    for field in ("paper_id", "metadata", "method", "experiments"):
        if field not in data:
            errors.append(f"Missing required top-level field: {field}")

    if "metadata" in data:
        _validate_metadata(data["metadata"], errors)

    if "method" in data:
        _validate_method(data["method"], errors)

    if "experiments" in data:
        _validate_experiments(data["experiments"], errors)

    if level == 2 and "analysis" in data:
        _validate_analysis(data["analysis"], errors)

    # Check extraction_level matches
    if "extraction_level" in data and data["extraction_level"] != level:
        errors.append(f"extraction_level is {data['extraction_level']} but expected {level}")

    return errors


def validate_or_raise(data: dict, level: int = 1) -> None:
    """Validate and raise ValidationError if invalid."""
    errors = validate_extraction(data, level)
    if errors:
        raise ValidationError(errors)


# -- field validators --------------------------------------------------------

def _validate_metadata(meta: dict, errors: list[str]) -> None:
    for field in ("title", "authors", "venue", "year"):
        if field not in meta:
            errors.append(f"metadata missing required field: {field}")
    if "authors" in meta and not isinstance(meta["authors"], list):
        errors.append("metadata.authors must be a list")
    if "year" in meta and not isinstance(meta["year"], int):
        errors.append("metadata.year must be an integer")


def _validate_method(method: dict, errors: list[str]) -> None:
    # Check source traceability on method_components
    for i, comp in enumerate(method.get("method_components", [])):
        if "source" not in comp or not comp["source"]:
            errors.append(f"method.method_components[{i}] missing source field")

    # Check theoretical_results enum
    valid_types = {"theorem", "lemma", "proposition", "bound", "guarantee"}
    for i, res in enumerate(method.get("theoretical_results", [])):
        if "type" in res and res["type"] not in valid_types:
            errors.append(f"method.theoretical_results[{i}].type '{res['type']}' not in {valid_types}")
        if "source" not in res or not res["source"]:
            errors.append(f"method.theoretical_results[{i}] missing source field")


def _validate_experiments(exp: dict, errors: list[str]) -> None:
    for field in ("datasets", "baselines", "metrics", "key_results"):
        items = exp.get(field, [])
        if not isinstance(items, list):
            errors.append(f"experiments.{field} must be a list")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            # All experiment sub-items require name+source or description+source
            if field in ("datasets", "baselines", "metrics"):
                if "name" not in item:
                    errors.append(f"experiments.{field}[{i}] missing 'name'")
            if "source" not in item or not item["source"]:
                errors.append(f"experiments.{field}[{i}] missing 'source'")


def _validate_analysis(analysis: dict, errors: list[str]) -> None:
    for i, a in enumerate(analysis.get("assumptions", [])):
        if "source" not in a or not a["source"]:
            errors.append(f"analysis.assumptions[{i}] missing source")
    for i, l in enumerate(analysis.get("limitations", [])):
        if "source" not in l or not l["source"]:
            errors.append(f"analysis.limitations[{i}] missing source")

    valid_rels = {"shared_dataset", "shared_baseline", "extends", "contradicts", "complements"}
    for i, ref in enumerate(analysis.get("anchor_cross_references", [])):
        if "relationship" in ref and ref["relationship"] not in valid_rels:
            errors.append(f"analysis.anchor_cross_references[{i}].relationship '{ref['relationship']}' invalid")
        if "source" not in ref or not ref["source"]:
            errors.append(f"analysis.anchor_cross_references[{i}] missing source")
