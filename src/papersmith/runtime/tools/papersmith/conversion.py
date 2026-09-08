"""Task-tree conversion for the paper-reconstruction contract.

Assembles the full Harbor task tree from the rendered templates, the material
assembly, and the private ground-truth source. Uses `contract.validate_task_tree`
for structural conformance. Compile proof is written to a staging dir OUTSIDE the
published task tree.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .contract import CANARY_GUID, render_template, validate_task_tree
from .sources import BlockedError

TEMPLATES = Path(__file__).parent / "templates"


def _render(name: str, variables: dict[str, str]) -> str:
    variables = {"canary": CANARY_GUID, **variables}
    return render_template((TEMPLATES / name).read_text(encoding="utf-8"), variables)


def build_task_tree(
    task_dir: Path,
    *,
    identifier: str,
    domain_tag: str,
    relevant_experience: str,
    config: dict,
    materials_dir: Path,
    ground_truth_tex: str,
    ground_truth_pdf: Path | None,
    research_overview_long: str,
    source_manifest: dict,
    texmf_dir: Path | None = None,
) -> dict:
    variables = {
        "domain_tag": domain_tag,
        "relevant_experience": relevant_experience,
        "title": config.get("title", identifier),
    }
    task_dir.mkdir(parents=True, exist_ok=True)
    environment = task_dir / "environment"
    solution = task_dir / "solution"
    tests = task_dir / "tests"
    environment.mkdir(exist_ok=True)
    solution.mkdir(exist_ok=True)
    tests.mkdir(exist_ok=True)
    (task_dir / "task.toml").write_text(_render("task.toml.j2", variables), encoding="utf-8")
    (task_dir / "instruction.md").write_text(_render("instruction.md.j2", variables), encoding="utf-8")

    (environment / "Dockerfile").write_text(_render("environment.Dockerfile", variables), encoding="utf-8")
    shutil.copytree(materials_dir, environment / "materials", dirs_exist_ok=True)
    (environment / "texmf").mkdir(parents=True, exist_ok=True)
    _copy_texmf(texmf_dir, environment / "texmf")

    solution = task_dir / "solution"
    (solution / "solve.sh").write_text(_render("solve.sh.j2", variables), encoding="utf-8")
    (solution / "normalize.py").write_text(_render("normalize.py", variables), encoding="utf-8")
    private = solution / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "main.tex").write_text(ground_truth_tex, encoding="utf-8")
    if ground_truth_pdf is None or not ground_truth_pdf.is_file():
        from .latex import compile_ground_truth_pdf

        references_bib = (materials_dir / "references.bib").read_text(encoding="utf-8")
        proof_dir = task_dir.parent / f"{task_dir.name}-template-proof"
        compiled = compile_ground_truth_pdf(ground_truth_tex, references_bib, proof_dir, "main", texmf_dir)
        ground_truth_pdf = compiled.get("pdf")
    if ground_truth_pdf is not None and ground_truth_pdf.is_file():
        shutil.copy2(ground_truth_pdf, private / "main.pdf")
    config_lines = [f"{key}: {value}" for key, value in config.items()]
    (private / "config.yaml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")

    tests = task_dir / "tests"
    (tests / "Dockerfile").write_text(_render("tests.Dockerfile", variables), encoding="utf-8")
    (tests / "test.sh").write_text(_render("test.sh", variables), encoding="utf-8")
    (tests / "test_state.py").write_text(_render("test_state.py", variables), encoding="utf-8")
    (tests / "grader_pwb.py").write_text(_render("grader_pwb.py", variables), encoding="utf-8")
    (tests / "texmf").mkdir(parents=True, exist_ok=True)
    _copy_texmf(texmf_dir, tests / "texmf")
    tprivate = tests / "private"
    tprivate.mkdir(parents=True, exist_ok=True)
    (tprivate / "ground_truth.tex").write_text(ground_truth_tex, encoding="utf-8")
    (tprivate / "research_overview_long.md").write_text(research_overview_long, encoding="utf-8")
    (tprivate / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    materials = materials_dir
    for name in ("figure_summary.txt", "table_summary.txt"):
        src = materials / name
        if src.is_file():
            shutil.copy2(src, tprivate / name)
    (tprivate / "ground_truth_sources").mkdir(exist_ok=True)

    return validate_task_tree(task_dir)


def _copy_texmf(texmf_dir: Path | None, dest: Path) -> None:
    if texmf_dir is not None and texmf_dir.is_dir():
        for path in texmf_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, dest / path.name)


def build_source_manifest(identifier: str, metadata: dict, source: dict) -> dict:
    return {
        "identifier": identifier,
        "title": metadata.get("title"),
        "authors": metadata.get("authors"),
        "doi": metadata.get("doi"),
        "license": metadata.get("license"),
        "year": metadata.get("year"),
        "source": source,
    }
