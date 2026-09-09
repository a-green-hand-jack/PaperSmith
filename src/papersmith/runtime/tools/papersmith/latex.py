"""Deterministic LaTeX surgery for the paper-reconstruction task.

Operates on an extracted arXiv source directory: locate the main `.tex`, probe
reducibility, derive a section-skeleton `template.tex`, extract the bibliography,
style files and referenced figures, and prove the template compiles. Unsupported
source forms are rejected with a recorded reason, never patched ad hoc.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from .sources import BlockedError

SHELL_ESCAPE_MARKERS = (
    "\\minted",
    "\\standaloneconfig",
    "shellescape",
    "\\lstinputlisting",
    "\\immediate\\write18",
)


def _balanced_block(text: str, start: int) -> tuple[str, int]:
    """Return the balanced `{...}` content starting at text[start] (a '{')."""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
    return text[start + 1 :], len(text)


def _extract_command(text: str, name: str) -> str | None:
    match = re.search(rf"\\{name}\s*(?:\[[^\]]*\])?\s*{{", text)
    if not match:
        return None
    content, _ = _balanced_block(text, match.end() - 1)
    return content


def find_main_tex(directory: Path) -> Path:
    tex_files = sorted(directory.rglob("*.tex"))
    if not tex_files:
        raise BlockedError("proposal", f"no .tex files in source directory: {directory}")
    for preferred in ("main.tex", "ms.tex", "manuscript.tex"):
        for path in tex_files:
            if path.name == preferred:
                return path
    if len(tex_files) == 1:
        return tex_files[0]
    for path in tex_files:
        if "\\begin{document}" in path.read_text(encoding="utf-8", errors="replace"):
            return path
    raise BlockedError("proposal", f"no main .tex identified in {directory}")


def probe_reducibility(directory: Path, main_tex: Path) -> dict:
    text = main_tex.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    for marker in SHELL_ESCAPE_MARKERS:
        if marker in text:
            issues.append(f"shell-escape-related construct: {marker}")
    if "\\documentclass" not in text:
        issues.append("missing \\documentclass")
    if "\\begin{document}" not in text or "\\end{document}" not in text:
        issues.append("not a complete LaTeX document")
    bib_files = sorted(directory.rglob("*.bib"))
    if not bib_files:
        issues.append("no .bib bibliography (unsupported source form)")
    return {
        "ok": not issues,
        "issues": issues,
        "bib_files": [str(p) for p in bib_files],
    }


def _remove_command(text: str, name: str) -> str:
    """Remove `\name{...}` or `\name[...]{...}` (balanced braces) occurrences."""
    pattern = re.compile(rf"\\{name}\s*(?:\[[^\]]*\])?\s*\{{")
    parts: list[str] = []
    pos = 0
    for match in pattern.finditer(text):
        _, end = _balanced_block(text, match.end() - 1)
        parts.append(text[pos : match.start()])
        pos = end
    parts.append(text[pos:])
    return "".join(parts)


def _detect_bibstyle(main_tex_text: str) -> str:
    """Reuse the source's \bibliographystyle when present, else infer from class."""
    match = re.search(r"\\bibliographystyle\s*\{([^}]+)\}", main_tex_text)
    if match:
        return match.group(1).strip()
    cls = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", main_tex_text)
    cname = (cls.group(1) if cls else "").lower()
    if "revtex" in cname or "aps" in cname:
        return "apsrev"
    if "elsarticle" in cname:
        return "elsarticle-num"
    if "ieeetran" in cname:
        return "IEEEtran"
    if "aastex" in cname or cname in ("aa", "aas"):
        return "aastex"
    return "plain"


INLINE_MAX_DEPTH = 5
INLINE_MAX_BYTES = 2 * 1024 * 1024


def inline_inputs(text: str, source_dir: Path, depth: int = 0) -> str:
    r"""Inline local \input/\include fragments so a template stands alone.

    A derived template is compiled and shipped away from the paper's source
    directory, so any fragment it pulls in must travel with it. Unresolvable
    targets are left untouched rather than guessed at, and recursion is bounded
    so a self-referential source cannot loop.
    """
    if depth >= INLINE_MAX_DEPTH or len(text) > INLINE_MAX_BYTES:
        return text

    def replace(match: re.Match[str]) -> str:
        target = match.group(2).strip()
        if not target or target.startswith(("/", "..")):
            return match.group(0)
        candidates = [source_dir / target]
        if not target.endswith(".tex"):
            candidates.append(source_dir / f"{target}.tex")
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(source_dir.resolve())
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                body = resolved.read_text(encoding="utf-8", errors="replace")
                return inline_inputs(body, source_dir, depth + 1)
        return match.group(0)

    return re.sub(r"\\(input|include)\s*\{([^}]*)\}", replace, text)


def uses_biblatex(text: str) -> bool:
    return bool(re.search(r"\\usepackage(\[[^\]]*\])?\{[^}]*biblatex", text)) or "\\addbibresource" in text


def bibliography_block(main_tex_text: str) -> list[str]:
    r"""The bibliography commands that match the source's own machinery.

    biblatex rejects \bibliographystyle outright, so emitting it unconditionally
    broke every biblatex paper at compile time.
    """
    if uses_biblatex(main_tex_text):
        return ["\\addbibresource{references.bib}", "\\printbibliography"]
    return [
        f"\\bibliographystyle{{{_detect_bibstyle(main_tex_text)}}}",
        "\\bibliography{references}",
    ]


def undefined_macros(log: str) -> list[str]:
    """Control sequences TeX reported as undefined, for stubbing."""
    names: list[str] = []
    lines = log.splitlines()
    for index, line in enumerate(lines):
        if "Undefined control sequence" not in line:
            continue
        for follow in lines[index + 1 : index + 4]:
            for match in re.finditer(r"\\([A-Za-z@]+)", follow):
                name = match.group(1)
                if name not in names:
                    names.append(name)
    return names


def stub_macros(text: str, names: list[str]) -> str:
    r"""Declare missing macros as no-ops ahead of \begin{document}."""
    if not names:
        return text
    stubs = "\n".join(f"\\providecommand{{\\{name}}}[1][]{{}}" for name in names)
    marker = "\\begin{document}"
    position = text.find(marker)
    if position == -1:
        return stubs + "\n" + text
    return text[:position] + stubs + "\n" + text[position:]


GRAPHICS_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps", ".gif", ".bmp", ".tif", ".tiff")


def copy_graphics(source_dir: Path, dest_dir: Path, limit_bytes: int = 64 * 1024 * 1024) -> int:
    r"""Copy the source's image files next to a template being compiled.

    Preambles and author blocks routinely \includegraphics small assets such as
    an ORCID badge. Those live in the paper's directory, so a template compiled
    anywhere else fails on a missing file — which is a packaging problem, not a
    property of the paper. Names are flattened to their basename because that is
    how \includegraphics refers to them once \graphicspath is gone.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    budget = limit_bytes
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in GRAPHICS_SUFFIXES:
            continue
        if path.is_symlink():
            continue
        size = path.stat().st_size
        if size > budget:
            break
        target = dest_dir / path.name
        if target.exists():
            continue
        shutil.copy2(path, target)
        budget -= size
        copied += 1
    return copied


def deduplicate_packages(text: str, package: str) -> str:
    r"""Keep only the first \usepackage of `package`, dropping later loads.

    LaTeX raises "Option clash" when the same package is requested twice with
    different options. Inlining fragments makes that easy to trigger, and the
    first load is the one whose options the rest of the preamble was written
    against.
    """
    pattern = re.compile(r"\\usepackage\s*(\[[^\]]*\])?\s*\{([^}]*)\}")
    seen = False
    out: list[str] = []
    position = 0
    for match in pattern.finditer(text):
        names = [n.strip() for n in match.group(2).split(",")]
        if package not in names:
            continue
        if not seen:
            seen = True
            continue
        # Drop this load: either the whole command, or just this name from a list.
        out.append(text[position : match.start()])
        if len(names) > 1:
            kept = ",".join(n for n in names if n != package)
            out.append(f"\\usepackage{match.group(1) or ''}{{{kept}}}")
        position = match.end()
    out.append(text[position:])
    return "".join(out)


def clashing_package(log: str) -> str | None:
    match = re.search(r"Option clash for package\s+([A-Za-z0-9@._-]+)", log)
    return match.group(1).rstrip(".") if match else None


def _declares(text: str, name: str) -> bool:
    r"""Whether `text` actually declares \<name>{...} or \<name>[...]{...}.

    A substring test is wrong here: "\title" also matches \titlerunning and
    \titleformat, so a paper using either was treated as already having a title,
    the title was dropped from the template, and \maketitle then failed with
    "No \title given".
    """
    return bool(re.search(rf"\\{name}\s*(?:\[[^\]]*\])?\s*\{{", text))


def derive_template(main_tex_text: str) -> str:
    doc_match = re.search(r"\\begin\{document\}", main_tex_text)
    preamble = main_tex_text[: doc_match.start()] if doc_match else ""
    body = main_tex_text[doc_match.end() :] if doc_match else ""

    # Balanced-brace section extraction so titles with nested braces/commands
    # (e.g. \texorpdfstring, math, \label) survive verbatim.
    structure: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(r"\\(subsubsection|subsection|section)\s*\{", main_tex_text):
        level = match.group(1)
        content, _ = _balanced_block(main_tex_text, match.end() - 1)
        name = content.strip()
        if name and (level, name) not in seen:
            seen.add((level, name))
            structure.append((level, name))

    # Keep title/author in the preamble verbatim; for revtex-style papers they
    # live in the body and must be re-emitted before \maketitle.
    title = "" if _declares(preamble, "title") else (_extract_command(body, "title") or "")
    author = "" if _declares(preamble, "author") else (_extract_command(body, "author") or "")

    # Emit an empty abstract in the same form the source uses.
    if "\\begin{abstract}" in main_tex_text:
        abstract_block = "\\begin{abstract}\n\\end{abstract}"
    elif "\\abstract{" in main_tex_text:
        abstract_block = "\\abstract{}"
    else:
        abstract_block = ""

    lines = [preamble.rstrip()]
    lines.append("\\begin{document}")
    # Preserving the source's front matter verbatim was measured against this
    # corpus: it recovered nothing and lost two papers to brace imbalance, so the
    # reconstruction stays.
    if title:
        lines.append("\\title{" + title + "}")
    if author:
        lines.append("\\author{" + author + "}")
    if abstract_block:
        lines.append(abstract_block)
    lines.append("\\maketitle")
    for level, name in structure:
        lines.append(f"\\{level}{{{name}}}")
    lines.extend(bibliography_block(main_tex_text))
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"


def extract_references(directory: Path) -> str:
    bib_files = sorted(directory.rglob("*.bib"))
    if not bib_files:
        raise BlockedError("proposal", "no .bib bibliography; reducibility probe must reject first")
    return bib_files[0].read_text(encoding="utf-8", errors="replace")


def extract_figures(directory: Path, main_tex_text: str, out_dir: Path) -> list[str]:
    copied: list[str] = []
    referenced = set(re.findall(r"\\includegraphics(?:\*)?(?:\[[^\]]*\])*\{([^}]+)\}", main_tex_text))
    for ref in referenced:
        name = Path(ref.strip())
        candidates = [directory / name, directory / name.with_suffix(name.suffix or ".pdf")]
        source = next((c for c in candidates if c.is_file()), None)
        if source is None:
            continue
        target = out_dir / source.relative_to(directory)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(str(target.relative_to(out_dir)))
    return copied


def extract_tables(main_tex_path: Path, main_tex_text: str, out_dir: Path) -> list[dict]:
    """Extract `table`/`table*` environments into per-table .tex files + inventory."""
    out_dir.mkdir(parents=True, exist_ok=True)
    inventory: list[dict] = []
    pattern = re.compile(r"\\begin\{(table\*?)\}(.*?)\\end\{\1\}", re.DOTALL)
    for index, match in enumerate(pattern.finditer(main_tex_text), 1):
        environment = match.group(1)
        block = match.group(0)
        caption = _extract_command(block, "caption")
        label = _extract_command(block, "label")
        line_start = main_tex_text[: match.start()].count("\n") + 1
        table_id = f"table-{index:03d}"
        content = block + "\n"
        public_path = f"tables/{table_id}.tex"
        (out_dir / f"{table_id}.tex").write_text(content, encoding="utf-8")
        inventory.append(
            {
                "id": table_id,
                "source_path": main_tex_path.name,
                "line_start": line_start,
                "environment": environment,
                "caption": caption,
                "label": label,
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "public_path": public_path,
            }
        )
    return inventory


def extract_style_files(directory: Path, texmf_dir: Path) -> list[str]:
    """Copy paper-local .sty/.cls/.bst/.clo/.cfg files into a texmf dir."""
    texmf_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for path in sorted(directory.rglob("*")):
        if path.suffix in (".sty", ".cls", ".bst", ".clo", ".cfg"):
            shutil.copy2(path, texmf_dir / path.name)
            copied.append(path.name)
    return copied


def _tex_env(texmf_dir: Path | None) -> dict | None:
    if texmf_dir is None:
        return None
    existing = os.environ.get("TEXINPUTS", "")
    return {
        **os.environ,
        "TEXINPUTS": f"{texmf_dir}//:{existing}",
        "BSTINPUTS": f"{texmf_dir}//:{existing}",
    }


def normalize_tex(text: str) -> str:
    text = re.sub(r"\\begin\{filecontents\}.*?\\end\{filecontents\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\\bibliography\{[^}]*\}", r"\\bibliography{references}", text)
    if "\\bibliographystyle" not in text:
        text = text.replace(
            "\\bibliography{references}",
            "\\bibliographystyle{elsarticle-num}\n\\bibliography{references}",
        )
    return text


# A pathological source can make a LaTeX pass spin indefinitely. At batch scale
# that is not a slow paper, it is a worker lost for the rest of the run, so every
# pass is bounded and a timeout is reported as a normal compile failure: the
# paper gets rejected and the shard moves on.
COMPILE_TIMEOUT_SECONDS = int(os.environ.get("PAPERSMITH_COMPILE_TIMEOUT", "180"))


def _run_compile(command: list[str], cwd: Path, env: dict) -> tuple[int, str, str]:
    """Run one compile pass. Returns (returncode, stdout, stderr).

    A timeout yields a non-zero code and a reason in stderr rather than an
    exception, so callers keep their single failure path.
    """
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            timeout=COMPILE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"compile pass exceeded {COMPILE_TIMEOUT_SECONDS}s: {' '.join(command)}"
    return result.returncode, result.stdout, result.stderr


def summarize_compile_log(log: str, limit: int = 800) -> str:
    """Pull the actual LaTeX errors out of a compile log.

    The tail of a pdflatex log is package-loading noise, so truncating to the
    last N characters reliably hides the one thing worth reading. TeX marks
    real errors with a leading "!", and the line after it usually carries the
    location, so keep those and fall back to the tail only when there is no
    error line at all.
    """
    lines = log.splitlines()
    picked: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith("!") or line.startswith("! LaTeX Error"):
            picked.append(line.strip())
            for follow in lines[index + 1 : index + 3]:
                if follow.strip():
                    picked.append(follow.strip())
            if sum(len(p) for p in picked) > limit:
                break
    if not picked:
        return log[-limit:]
    return " | ".join(dict.fromkeys(picked))[:limit]


def _compile_commands(name: str) -> list[list[str]]:
    return [
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", f"{name}.tex"],
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", f"{name}.tex"],
        ["bibtex", name],
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", f"{name}.tex"],
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", f"{name}.tex"],
    ]


def compile_source(source_dir: Path, main_tex: Path, out_dir: Path) -> dict:
    """Build the paper's own main file, in a copy of its own directory.

    This is the honest reducibility test. A paper published on arXiv was built
    there, so if its source still builds here, any downstream compile failure
    belongs to this pipeline and must not be recorded as a bad paper. The copy
    keeps the build from writing into the fetched source we hash as evidence.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "source"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(source_dir, work)
    name = main_tex.stem
    env = _tex_env(None)
    log: list[str] = []
    for command in _compile_commands(name):
        returncode, stdout, stderr = _run_compile(command, work, env)
        if command[0] == "bibtex":
            continue
        log.append(" ".join(command))
        if returncode != 0:
            log.append(stdout[-2000:])
            log.append(stderr[-2000:])
            break
    pdf = work / f"{name}.pdf"
    tex_log = work / f"{name}.log"
    if tex_log.is_file():
        log.append(tex_log.read_text(encoding="utf-8", errors="replace")[-4000:])
    return {"ok": pdf.is_file() and pdf.stat().st_size > 0, "log": "\n".join(log), "pdf": pdf if pdf.is_file() else None}


def compile_ground_truth_pdf(
    tex_text: str, bib_text: str, out_dir: Path, name: str = "main", texmf_dir: Path | None = None
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.tex").write_text(normalize_tex(tex_text), encoding="utf-8")
    (out_dir / "references.bib").write_text(bib_text, encoding="utf-8")
    env = _tex_env(texmf_dir)
    log: list[str] = []
    for command in _compile_commands(name):
        returncode, stdout, stderr = _run_compile(command, out_dir, env)
        if command[0] == "bibtex":
            continue
        log.append(" ".join(command))
        if returncode != 0:
            log.append(stdout[-2000:])
            log.append(stderr[-2000:])
            return {"ok": False, "log": "\n".join(log), "pdf": None}
    pdf = out_dir / f"{name}.pdf"
    ok = pdf.is_file() and pdf.stat().st_size > 0
    return {"ok": ok, "log": "\n".join(log), "pdf": pdf if ok else None}


def compile_template(
    template_text: str,
    references_text: str,
    out_dir: Path,
    texmf_dir: Path | None = None,
    assets_dir: Path | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    if assets_dir is not None and assets_dir.is_dir():
        copy_graphics(assets_dir, out_dir)
    (out_dir / "template.tex").write_text(template_text, encoding="utf-8")
    (out_dir / "references.bib").write_text(references_text, encoding="utf-8")
    env = _tex_env(texmf_dir)
    log: list[str] = []
    for command in _compile_commands("template"):
        returncode, stdout, stderr = _run_compile(command, out_dir, env)
        if command[0] == "bibtex":
            continue
        log.append(" ".join(command))
        if returncode != 0:
            log.append(stdout[-2000:])
            log.append(stderr[-2000:])
            return {"ok": False, "log": "\n".join(log)}
    pdf = out_dir / "template.pdf"
    return {"ok": pdf.is_file() and pdf.stat().st_size > 0, "log": "\n".join(log)}
