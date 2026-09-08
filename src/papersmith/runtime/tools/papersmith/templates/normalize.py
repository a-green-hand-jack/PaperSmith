"""Oracle normalization: reproduce a compilable submission from ground truth.

Deterministic only. Reads the ground-truth main.tex from the private dir and the
bibliography from the public materials dir; normalizes the bibliography filename
to references.bib, drops filecontents blocks, and copies both into the
submission directory. Per-paper LaTeX pathologies are rejected upstream by the
reducibility probe, never patched here.
"""
import re
import shutil
import sys
from pathlib import Path


def normalize(materials_dir: Path, submission: Path, private_dir: Path) -> None:
    main_tex = private_dir / "main.tex"
    references = materials_dir / "references.bib"
    if not main_tex.is_file():
        raise SystemExit(f"ground-truth main.tex missing: {main_tex}")
    if not references.is_file():
        raise SystemExit(f"references.bib missing: {references}")
    text = main_tex.read_text(encoding="utf-8", errors="replace")
    # Drop filecontents blocks (the bibliography must be an external file).
    text = re.sub(r"\\begin\{filecontents\}.*?\\end\{filecontents\}", "", text, flags=re.DOTALL)
    # Normalize the bibliography reference to references.bib.
    text = re.sub(r"\\bibliography\{[^}]*\}", r"\\bibliography{references}", text)
    if "\\bibliographystyle" not in text:
        text = text.replace(
            "\\bibliography{references}",
            "\\bibliographystyle{elsarticle-num}\n\\bibliography{references}",
        )
    (submission / "main.tex").write_text(text, encoding="utf-8")
    shutil.copy2(references, submission / "references.bib")
    # Copy figures so both bare and figures/-prefixed \includegraphics paths resolve.
    figures = materials_dir / "figures"
    if figures.is_dir():
        shutil.copytree(figures, submission / "figures", dirs_exist_ok=True)
        for path in figures.iterdir():
            if path.is_file():
                shutil.copy2(path, submission / path.name)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: normalize.py <materials-dir> <submission-dir> <private-dir>", file=sys.stderr)
        return 2
    normalize(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
