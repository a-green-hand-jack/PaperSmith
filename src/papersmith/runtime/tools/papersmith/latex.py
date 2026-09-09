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


def bibliography_preamble(main_tex_text: str) -> list[str]:
    r"""Bibliography commands that must sit before \begin{document}.

    \addbibresource is \@onlypreamble: emitting it in the body aborts the
    compile with "Can be used only in preamble", which is what happened to every
    biblatex paper in the corpus.
    """
    if uses_biblatex(main_tex_text):
        return ["\\addbibresource{references.bib}"]
    return []


def bibliography_block(main_tex_text: str) -> list[str]:
    r"""The bibliography commands that belong in the body.

    biblatex rejects \bibliographystyle outright, so emitting it unconditionally
    broke every biblatex paper at compile time.

    No \nocite{*} here. The template has no prose and therefore no \cite, so
    bibtex writes a thebibliography with no \bibitem -- an empty list, which
    LaTeX rejects as "Something's wrong--perhaps a missing \item". Emitting
    \nocite{*} unconditionally fixes those seven papers and breaks fifteen
    others, measured: typesetting every entry in a paper's .bib surfaces each
    entry LaTeX cannot set as-is ("Misplaced alignment tab character &",
    "Unicode character U+2212", "Missing $ inserted"). It is applied as a repair
    escalation instead, so only the papers that hit the empty list pay for it.
    """
    if uses_biblatex(main_tex_text):
        return ["\\printbibliography"]
    return [
        f"\\bibliographystyle{{{_detect_bibstyle(main_tex_text)}}}",
        "\\bibliography{references}",
    ]


def empty_bibliography(log: str) -> bool:
    r"""Whether the compile died on a thebibliography holding no \bibitem."""
    return r"perhaps a missing \item" in log or "Empty `thebibliography' environment" in log


def cite_everything(template_text: str) -> str:
    r"""Add \nocite{*} so bibtex emits at least one \bibitem."""
    if r"\nocite" in template_text:
        return template_text
    for anchor in (r"\printbibliography", r"\bibliography{references}"):
        position = template_text.find(anchor)
        if position != -1:
            return template_text[:position] + "\\nocite{*}\n" + template_text[position:]
    return template_text


def drop_bibliography(template_text: str) -> str:
    r"""Remove the bibliography commands entirely.

    Last resort for a paper whose .bib cannot be typeset at all: a template
    without a reference list still compiles and still states the writing task.
    """
    out = []
    for line in template_text.splitlines():
        stripped = line.strip()
        if stripped.startswith((r"\nocite", r"\printbibliography", r"\bibliography{",
                                r"\bibliographystyle{", r"\addbibresource{")):
            continue
        out.append(line)
    return "\n".join(out) + "\n"


# Names that must never be stubbed. Redefining any of these as a no-op does not
# rescue a template, it destroys it: \end as a no-op unbalances every environment
# in the document. They appear in the log because TeX reports the line it was
# reading, not only the missing name.
NEVER_STUB = frozenset({
    "begin", "end", "item", "par", "documentclass", "usepackage", "input",
    "include", "newcommand", "renewcommand", "providecommand", "def", "let",
    "expandafter", "csname", "endcsname", "makeatletter", "makeatother",
    "relax", "write", "immediate", "the", "protect",
})


def undefined_macros(log: str) -> list[str]:
    r"""Control sequences TeX reported as undefined, for stubbing.

    Two filters, both learned from papers this lost. Structural primitives are
    excluded because stubbing \end is fatal, not corrective. Internal names
    containing @ are excluded because \providecommand{\@foo} outside
    \makeatletter parses as \@ followed by text, and the compile then dies on
    "Command \@ already defined" -- a failure invented entirely by the repair.
    """
    names: list[str] = []
    lines = log.splitlines()
    for index, line in enumerate(lines):
        if "Undefined control sequence" not in line:
            continue
        for follow in lines[index + 1 : index + 4]:
            for match in re.finditer(r"\\([A-Za-z@]+)", follow):
                name = match.group(1)
                if "@" in name or name in NEVER_STUB or name in names:
                    continue
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


def pass_package_options(text: str, package: str) -> str:
    r"""Hoist a package's options to \PassOptionsToPackage before \documentclass.

    The other shape of "Option clash": the document class (or a package it pulls
    in) loads the package first with no options, and the preamble's explicit
    \usepackage[opts]{pkg} then clashes with it. There is no duplicate
    \usepackage to drop, so deduplication is a no-op -- four papers in the corpus
    failed here with xcolor loaded once in the source and once by revtex. Hoisting
    recovers two of them with no losses; the rest clash for reasons this does not
    reach, and stay rejected under a label that names the real error.

    Requesting the options before \documentclass makes them part of that first
    load, which is the remedy LaTeX itself documents.
    """
    pattern = re.compile(r"\\usepackage\s*\[([^\]]*)\]\s*\{([^}]*)\}")
    options = ""
    replacements: list[tuple[int, int, str]] = []
    for match in pattern.finditer(text):
        names = [n.strip() for n in match.group(2).split(",")]
        if package not in names:
            continue
        options = match.group(1)
        remaining = [n for n in names if n != package]
        body = f"\\usepackage{{{','.join(remaining)}}}" if remaining else ""
        replacements.append((match.start(), match.end(), body))
    if not options:
        return text
    for start, stop, body in reversed(replacements):
        text = text[:start] + body + text[stop:]
    directive = f"\\PassOptionsToPackage{{{options}}}{{{package}}}\n"
    class_match = re.search(r"\\documentclass\s*(\[[^\]]*\])?\s*\{[^}]*\}", text)
    if not class_match:
        return directive + text
    return text[: class_match.start()] + directive + text[class_match.start() :]


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


# Front-matter commands carried verbatim, as a block. A document class treats
# these as one unit: an author without its affiliation is an error in AASTeX, and
# revtex's \maketitle reads counters that only \collaboration and friends set.
FRONT_MATTER_COMMANDS = (
    "author", "affiliation", "altaffiliation", "affil", "affiliations",
    "address", "email", "thanks", "collaboration", "homepage", "institute",
    "orcid", "date", "correspondingauthor", "nocollaboration",
)


def _front_matter_block(body: str) -> list[str]:
    r"""The source's author/affiliation commands, in order, verbatim.

    Scanning stops at \maketitle (or the first sectioning command) so an \email
    buried in the paper's prose is not mistaken for front matter.
    """
    end = len(body)
    for stop in (r"\\maketitle", r"\\section\b", r"\\chapter\b"):
        match = re.search(stop, body)
        if match:
            end = min(end, match.start())
    region = body[:end]

    spans: list[tuple[int, int]] = []
    for name in FRONT_MATTER_COMMANDS:
        for match in re.finditer(rf"\\{name}\s*(?:\[[^\]]*\])?\s*\{{", region):
            _, stop_index = _balanced_block(region, match.end() - 1)
            spans.append((match.start(), stop_index))
    spans.sort()

    # Drop spans nested inside another. \author{...} routinely contains \thanks
    # and \orcid for each author, and re-emitting those as standalone commands
    # after the author block duplicates them outside the scope that defines them.
    block: list[str] = []
    covered_to = -1
    for start, stop in spans:
        if start < covered_to:
            continue
        covered_to = stop
        text = region[start:stop]
        # Carrying text verbatim only works if it stands alone. _balanced_block
        # runs to end-of-string when the braces never close, and an unbalanced
        # capture breaks the whole template with errors invented by the repair
        # itself: "File ended while scanning use of \@affiliation", "Extra }".
        # An unbalanced span is dropped rather than emitted.
        if text.count("{") != text.count("}"):
            continue
        if text not in block:
            block.append(text)
    return block


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
    # Only the lone \author is carried. Lifting the whole author/affiliation block
    # verbatim was tried and measured against this corpus: it rescued the papers
    # whose class demands an affiliation, and broke eighteen others, for a net of
    # zero. Brace counting cannot tell a real closing brace from one a % comment
    # hides, so a "balanced" capture is routinely unbalanced to TeX, and the
    # template then fails with errors the repair invented: "File ended while
    # scanning use of \@affiliation", "Misplaced alignment tab character &".
    # Carrying front matter needs a real tokenizer, not a regex; until then the
    # classes that demand affiliations stay rejected, honestly labelled.
    author_block: list[str] = []
    if not _declares(preamble, "author"):
        lone = _extract_command(body, "author")
        if lone:
            author_block = ["\\author{" + lone + "}"]

    # Emit an empty abstract in the same form the source uses.
    if "\\begin{abstract}" in main_tex_text:
        abstract_block = "\\begin{abstract}\n\\end{abstract}"
    elif "\\abstract{" in main_tex_text:
        abstract_block = "\\abstract{}"
    else:
        abstract_block = ""

    head = preamble.rstrip()
    # \maketitle is always emitted, and it aborts with "No \title given" unless a
    # \title exists. When neither the preamble nor the body yielded one, an empty
    # placeholder in the preamble is the honest stand-in: the template is what the
    # writer fills in, and seven papers were rejected over this alone.
    if not title and not _declares(preamble, "title"):
        head += "\n\\title{}"
    lines = [head]
    lines.extend(bibliography_preamble(main_tex_text))
    lines.append("\\begin{document}")
    # Preserving the source's front matter verbatim was measured against this
    # corpus: it recovered nothing and lost two papers to brace imbalance, so the
    # reconstruction stays.
    if title:
        lines.append("\\title{" + title + "}")
    lines.extend(author_block)
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


STYLE_SUFFIXES = (".sty", ".cls", ".bst", ".clo", ".cfg", ".def", ".ldf", ".bbx", ".cbx", ".lbx")


def extract_style_files(directory: Path, texmf_dir: Path) -> list[str]:
    r"""Copy paper-local style files into a texmf dir, keeping their layout.

    Both the flattened name and the original relative path are provided, because
    sources disagree about which one they ask for: a paper doing
    \usepackage{icml2026_style/icml2026} needs the subdirectory to survive, while
    a paper whose class sits in a subdirectory but is loaded by bare name needs
    the flattened copy. Flattening alone lost two papers to "File
    `icml2026_style/icml2026.sty' not found"; keeping only the tree would lose
    the others.
    """
    texmf_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix not in STYLE_SUFFIXES:
            continue
        relative = path.relative_to(directory)
        if relative.parent != Path("."):
            nested = texmf_dir / relative
            nested.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, nested)
            copied.append(str(relative))
        flat = texmf_dir / path.name
        if not flat.exists():
            shutil.copy2(path, flat)
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
