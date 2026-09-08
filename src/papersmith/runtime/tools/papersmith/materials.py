"""Material construction for the paper-reconstruction task.

The model session (read-only) returns a structured JSON: the short public
`research_overview.md`, the long private overview, and per-asset figure/table
captions. The controller validates the fixed overview headings and asset
coverage, then deterministically assembles `environment/materials/`. Models
never write task files directly.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .sources import BlockedError

OVERVIEW_HEADINGS = [
    "# Title",
    "## Research Question or Hypothesis",
    "## Approach",
    "## Key Findings",
    "## Takeaway",
]

# Structural requirement (lenient on the exact title heading text).
_STRUCTURE_CHECKS = [
    ("title heading (# )", lambda t: re.search(r"(?m)^#\s+", t) is not None),
    ("## Research Question or Hypothesis", lambda t: "## Research Question or Hypothesis" in t),
    ("## Approach", lambda t: "## Approach" in t),
    ("## Key Findings", lambda t: "## Key Findings" in t),
    ("## Takeaway", lambda t: "## Takeaway" in t),
]


def build_materials_prompt(
    source_text: str,
    figures: list[str],
    table_inventory: list[dict],
    domain: str,
) -> str:
    tables_desc = [{"id": t.get("id"), "caption": t.get("caption")} for t in table_inventory]
    return (
        "You are the material-construction role for a PaperSmith run. Using ONLY the paper "
        "text below, produce the research overview and per-asset captions/descriptions. Do not call tools, "
        "read files, or write files; reply with a JSON object only. Do not invent facts.\n"
        f"Domain: {domain}\n"
        "Output JSON with exactly these keys:\n"
        '  "overview_short": markdown with exactly these headings in order: '
        f"{' -> '.join(OVERVIEW_HEADINGS)} (plus one '## <Domain> Significance' heading)\n"
        '  "overview_long": a longer private markdown version of the same overview\n'
        '  "figures": [{"file": "<filename>", "caption": "<caption>"}]\n'
        '  "tables": [{"id": "<table id>", "caption": "<description of what the table reports>"}]\n'
        f"Extracted figures to caption: {json.dumps(figures)}\n"
        f"Extracted tables to describe (id + LaTeX caption): {json.dumps(tables_desc, ensure_ascii=False)}\n\n"
        "Paper text:\n"
        f"{source_text[:60000]}"
    )


def validate_materials_output(data: dict) -> dict:
    import re

    issues: list[str] = []
    if not isinstance(data, dict):
        return {"valid": False, "issues": ["materials output is not an object"]}
    overview = data.get("overview_short") or ""
    for label, check in _STRUCTURE_CHECKS:
        if not check(overview):
            issues.append(f"overview missing: {label}")
    if not (data.get("overview_long") or "").strip():
        issues.append("overview_long is empty")
    if not isinstance(data.get("figures"), list) or not isinstance(data.get("tables"), list):
        issues.append("figures/tables must be lists")
    return {"valid": not issues, "issues": issues}


def _asset_summary(assets: list[dict], key: str = "file") -> str:
    lines = []
    for asset in assets:
        if isinstance(asset, dict):
            lines.append(f"{asset.get(key, '?')}: {asset.get('caption', '')}")
    return "\n".join(lines) + ("\n" if lines else "")


def _copy_dir(src: Path | None, dest: Path) -> None:
    if src is not None and src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)


def assemble_materials(
    materials_dir: Path,
    output: dict,
    references_bib: str,
    template_tex: str,
    agents_md: str,
    figures_dir: Path | None = None,
    tables_dir: Path | None = None,
    code_dir: Path | None = None,
    table_inventory: list[dict] | None = None,
) -> dict:
    materials_dir.mkdir(parents=True, exist_ok=True)
    (materials_dir / "research_overview.md").write_text(
        (output.get("overview_short") or "").strip() + "\n", encoding="utf-8"
    )
    (materials_dir / "references.bib").write_text(references_bib, encoding="utf-8")
    (materials_dir / "template.tex").write_text(template_tex, encoding="utf-8")
    (materials_dir / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    (materials_dir / "figure_summary.txt").write_text(
        _asset_summary(output.get("figures") or [], "file"), encoding="utf-8"
    )
    (materials_dir / "table_summary.txt").write_text(
        _asset_summary(output.get("tables") or [], "id"), encoding="utf-8"
    )
    (materials_dir / "table_inventory.json").write_text(
        json.dumps({"schema_version": 1, "tables": table_inventory or []}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (materials_dir / "figures").mkdir(exist_ok=True)
    _copy_dir(figures_dir, materials_dir / "figures")
    (materials_dir / "tables").mkdir(exist_ok=True)
    _copy_dir(tables_dir, materials_dir / "tables")
    (materials_dir / "code").mkdir(exist_ok=True)
    _copy_dir(code_dir, materials_dir / "code")
    return {"materials_dir": str(materials_dir), "overview_headings": OVERVIEW_HEADINGS}


def extract_pdf_text(pdf_path: Path, timeout: int = 300) -> dict:
    """Extract full-document text from a local PDF via Bohrium Uni-Parser."""
    from .sources import _run_bohr

    if not pdf_path.is_file():
        raise BlockedError("materials", f"source PDF not found: {pdf_path}")
    submit = _run_bohr(["pdf", "parse", "--file", str(pdf_path), "--sync", "--textual", "2"], timeout=timeout)
    token = (submit.get("data") or {}).get("token")
    if not token:
        raise BlockedError("materials", "bohr pdf parse returned no task token")
    result = _run_bohr(["pdf", "result", str(token), "--formatted", "plain"], timeout=timeout)
    content = (result.get("data") or {}).get("content") or ""
    import hashlib

    return {
        "text": content,
        "bytes": len(content.encode("utf-8")),
        "source_pdf": str(pdf_path),
        "evidence": {
            "source": "bohr-pdf-parse",
            "task_token": token,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        },
    }
