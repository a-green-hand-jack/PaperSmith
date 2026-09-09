"""Phase orchestration for the paper-reconstruction pipeline.

Wires deterministic acquisition, LaTeX surgery, material assembly, task-tree
conversion, review gates, and acceptance into a single fixed-paper flow. Each
phase records evidence to the run workspace; model sessions are read-only and
their outputs are validated before persistence.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import latex
from .acceptance import build_acceptance_request, write_acceptance_request
from .backends import DEFAULT_BACKEND, extract_json, run_phase
from .config import domain_profile
from .conversion import build_source_manifest, build_task_tree
from .contract import validate_task_tree
from .ledger import ledger_dir, load_excluded, record_deferred, record_rejected, record_used
from .materials import assemble_materials, build_materials_prompt, validate_materials_output
from .review import run_gate
from .sources import BlockedError, discover_candidates, fetch_arxiv_source, resolve_identifier
from .state import RunState


def _slug(identifier: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._-]", "_", identifier)[:64]


def run_ledger(state: RunState) -> dict:
    """Read the append-only event log to see what this run already produced.

    The event log is the run's own record, so resume derives progress from
    evidence rather than from a stored counter that a crash could desynchronise.
    A paper counts as done only when its task tree and acceptance request are
    both still on disk.
    """
    completed: dict[str, str] = {}
    rejected: dict[str, str] = {}
    events = state.root / "events.jsonl"
    if events.is_file():
        for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            paper = record.get("paper")
            if not isinstance(paper, str) or not paper:
                continue
            if record.get("event") == "acceptance_requested":
                completed[paper] = _slug(paper)
                rejected.pop(paper, None)
            elif record.get("event") == "paper_rejected" and paper not in completed:
                rejected[paper] = str(record.get("reason") or "")
    for paper, slug in list(completed.items()):
        tree = state.root / "tasks" / slug
        request = state.root / "acceptance" / f"{slug}-request.json"
        if not tree.is_dir() or not request.is_file():
            del completed[paper]
    return {"completed": completed, "rejected": rejected}


def run_fixed(root: Path, spec, args, resume: bool = False) -> dict:
    state = RunState.load(root)
    state.acquire_lock()
    try:
        papers = spec.papers or []
        if not papers:
            raise BlockedError("proposal", "fixed selection requires --paper")
        ledger = run_ledger(state) if resume else {"completed": {}, "rejected": {}}
        task_summaries: list[dict] = []
        errors: list[dict] = []
        reused: list[str] = []

        for paper in papers:
            if paper in ledger["completed"]:
                slug = ledger["completed"][paper]
                reused.append(paper)
                task_summaries.append(
                    {
                        "paper": paper,
                        "task_dir": str(state.root / "tasks" / slug),
                        "reused": True,
                        "acceptance_requested": True,
                    }
                )
                state.append_event("task_reused", paper=paper, slug=slug)
                continue
            try:
                summary = _build_one(state, spec, args, paper)
                task_summaries.append(summary)
            except BlockedError as exc:
                errors.append({"paper": paper, "reason": exc.reason})
                state.append_event("paper_rejected", paper=paper, reason=exc.reason)
            except Exception as exc:  # noqa: BLE001 - one paper must not end the run
                reason = f"unexpected {type(exc).__name__}: {exc}"[:300]
                errors.append({"paper": paper, "reason": reason})
                state.append_event("paper_rejected", paper=paper, reason=reason)

        ok = bool(task_summaries)
        state.data["status"] = "blocked"
        state.data["phase"] = "acceptance" if ok else "proposal"
        state.data["blocking_reason"] = (
            "task produced; real Harbor acceptance pending"
            if ok
            else "; ".join(e["reason"] for e in errors)
        )
        state.save()
        return {"ok": ok, "tasks": task_summaries, "errors": errors, "reused": reused}
    finally:
        state.release_lock()


def run_discovery(root: Path, spec, args, resume: bool = False) -> dict:
    """Discover arXiv candidates by domain, then build until `count` tasks."""
    state = RunState.load(root)
    state.acquire_lock()
    try:
        profile = domain_profile(spec.domain)
        ledger = run_ledger(state) if resume else {"completed": {}, "rejected": {}}
        # Papers already built or already rejected must not be paid for twice,
        # by this run or by any sibling worker sharing the batch ledger.
        shared = ledger_dir(getattr(args, "ledger", None))
        seen = set(ledger["completed"]) | set(ledger["rejected"]) | load_excluded(shared)
        # A shard that already met its target needs no candidates. Querying
        # anyway wastes API budget and, worse, puts a network call on the path of
        # a run that has nothing left to do.
        at_target = len(ledger["completed"]) >= spec.count
        candidates = (
            []
            if at_target
            else discover_candidates(
                profile["arxiv_categories"],
                spec.count,
                shard=getattr(args, "shard", None),
                exclude=seen,
            )
        )
        if not candidates and not at_target:
            raise BlockedError("proposal", "arXiv discovery returned no unseen candidates")
        state.append_event(
            "discovery_started", domain=spec.domain, candidates=len(candidates), target=spec.count
        )
        task_summaries: list[dict] = []
        errors: list[dict] = []
        considered = 0
        # Tasks this run already produced count toward the target, so a resumed
        # batch tops up to `count` instead of building a second full batch.
        for paper, slug in sorted(ledger["completed"].items()):
            task_summaries.append(
                {
                    "paper": paper,
                    "task_dir": str(state.root / "tasks" / slug),
                    "reused": True,
                    "acceptance_requested": True,
                }
            )
        reused = len(task_summaries)
        for identifier in candidates:
            if len(task_summaries) >= spec.count:
                break
            considered += 1
            try:
                summary = _build_one(state, spec, args, identifier)
                task_summaries.append(summary)
                state.append_event("task_built", paper=identifier, count=len(task_summaries))
                record_used(shared, identifier, summary.get("task_dir", ""), spec.domain)
            except BlockedError as exc:
                errors.append({"paper": identifier, "reason": exc.reason})
                if getattr(exc, "retryable", False):
                    # Never judged, so never excluded: a throttled upstream must
                    # not cost this paper every later run of the batch.
                    state.append_event("paper_deferred", paper=identifier, reason=exc.reason)
                    record_deferred(shared, identifier, exc.reason, spec.domain)
                else:
                    state.append_event("paper_rejected", paper=identifier, reason=exc.reason)
                    record_rejected(shared, identifier, exc.reason, spec.domain)
            except Exception as exc:  # noqa: BLE001 - one paper must not end the shard
                reason = f"unexpected {type(exc).__name__}: {exc}"[:300]
                errors.append({"paper": identifier, "reason": reason})
                state.append_event("paper_rejected", paper=identifier, reason=reason)
                record_rejected(shared, identifier, reason, spec.domain)

        ok = len(task_summaries) >= spec.count
        state.data["status"] = "blocked"
        state.data["phase"] = "acceptance" if ok else "proposal"
        state.data["blocking_reason"] = (
            f"produced {len(task_summaries)}/{spec.count} tasks; real Harbor acceptance pending"
            if ok
            else f"produced {len(task_summaries)}/{spec.count} tasks; "
            + "; ".join(e["reason"] for e in errors[-3:])
        )
        state.save()
        return {
            "ok": ok,
            "selection": "discovery",
            "domain": spec.domain,
            "target": spec.count,
            "candidates_considered": considered,
            "shard": getattr(args, "shard", None),
            "reused": reused,
            "tasks": task_summaries,
            "errors": errors,
        }
    finally:
        state.release_lock()


def _build_one(state: RunState, spec, args, paper: str) -> dict:
    identifier = str(paper)
    slug = _slug(identifier)
    profile = domain_profile(spec.domain)
    sources_dir = state.root / "stages" / "proposal" / "sources" / slug

    # 1. resolve metadata + fetch source bundle
    metadata = resolve_identifier(identifier)
    fetched = fetch_arxiv_source(identifier, sources_dir)
    state.append_event("source_fetched", paper=identifier, sha256=fetched["sha256"])

    # 2. reducibility probe + LaTeX surgery
    main_tex = latex.find_main_tex(sources_dir)
    probe = latex.probe_reducibility(sources_dir, main_tex)
    if not probe["ok"]:
        raise BlockedError("proposal", "not reducible: " + "; ".join(probe["issues"]))
    main_tex_text = main_tex.read_text(encoding="utf-8", errors="replace")
    references_bib = latex.extract_references(sources_dir)
    texmf_dir = state.root / "stages" / "materials" / "texmf"
    latex.extract_style_files(sources_dir, texmf_dir)

    # A paper on arXiv demonstrably builds: arXiv produced its PDF. So a template
    # that will not compile is this pipeline's defect, not a property of the
    # paper, and it must be repaired rather than used as grounds for rejection.
    # Fragments are inlined first so the template stands alone in the delivered
    # task, which never ships the paper's source directory.
    inlined = latex.inline_inputs(main_tex_text, sources_dir)
    template_tex = latex.derive_template(inlined)
    # Per-paper proof directory: a shared one let each paper overwrite the
    # previous paper's compile log, so the dominant rejection bucket could not
    # be diagnosed after the fact.
    proof_dir = state.root / "stages" / "materials" / "template-proof" / slug
    # The paper's own images travel with the template: a preamble that includes a
    # badge or logo must still build away from the source directory.
    template_proof = latex.compile_template(
        template_tex, references_bib, proof_dir, texmf_dir, assets_dir=sources_dir
    )
    repairs: list[str] = []

    def recompile() -> dict:
        return latex.compile_template(
            template_tex, references_bib, proof_dir, texmf_dir, assets_dir=sources_dir
        )

    if not template_proof["ok"]:
        # Escalation 1: the same package loaded twice with different options.
        # Inlining fragments makes this easy to trigger; the first load wins.
        clash = latex.clashing_package(template_proof["log"])
        if clash:
            template_tex = latex.deduplicate_packages(template_tex, clash)
            template_proof = recompile()
            if template_proof["ok"]:
                repairs.append(f"deduplicated package: {clash}")

    if not template_proof["ok"]:
        # Escalation 2: declare macros TeX reported as undefined. These are
        # typically defined in source the derivation stripped.
        missing = latex.undefined_macros(template_proof["log"])
        if missing:
            template_tex = latex.stub_macros(template_tex, missing)
            template_proof = recompile()
            if template_proof["ok"]:
                repairs.append(f"stubbed undefined macros: {', '.join(missing[:8])}")

    if not template_proof["ok"] and latex.empty_bibliography(template_proof["log"]):
        # Escalation 3: the template has no prose, so it cites nothing, so bibtex
        # writes a thebibliography with no \bibitem and LaTeX rejects the empty
        # list. \nocite{*} is applied only here, never by default: typesetting
        # every entry of a paper's .bib rescues these papers and breaks fifteen
        # others whose entries LaTeX cannot set as-is.
        template_tex = latex.cite_everything(template_tex)
        template_proof = recompile()
        if template_proof["ok"]:
            repairs.append("cited all references to fill an empty bibliography")

    if not template_proof["ok"] and latex.empty_bibliography(template_proof["log"]):
        # Escalation 4: that .bib cannot be typeset at all. A template without a
        # reference list still compiles and still states the writing task, which
        # beats discarding a usable paper over its bibliography.
        template_tex = latex.drop_bibliography(template_tex)
        template_proof = recompile()
        if template_proof["ok"]:
            repairs.append("dropped an unusable bibliography")

    if not template_proof["ok"]:
        # Still failing. Classify the loss honestly by asking whether the paper
        # itself builds, so a derivation defect is never filed as a bad paper.
        source_build = latex.compile_source(
            sources_dir, main_tex, state.root / "stages" / "proposal" / "source-build" / slug
        )
        detail = latex.summarize_compile_log(template_proof["log"])
        if not source_build["ok"]:
            raise BlockedError(
                "proposal",
                "source does not build: " + latex.summarize_compile_log(source_build["log"]),
            )
        raise BlockedError(
            "proposal",
            "template derivation failed (source builds, so this is a PaperSmith defect): " + detail,
        )

    if repairs:
        state.append_event("template_repaired", paper=identifier, repairs=repairs)
    state.append_event("template_derived", paper=identifier, compiles=True)

    # 3. materials: model writes overview + captions (read-only session)
    figures = latex.extract_figures(
        sources_dir, main_tex_text, state.root / "stages" / "materials" / "figures"
    )
    tables_dir = state.root / "stages" / "materials" / "tables"
    table_inventory = latex.extract_tables(main_tex, main_tex_text, tables_dir)
    prompt = build_materials_prompt(main_tex_text, figures, table_inventory, profile["materials_domain"])
    output: dict = {}
    validation = {"valid": False, "issues": ["no attempt"]}
    session = {"fingerprint": None}
    model_failure = ""
    for attempt in range(3):
        session = run_phase(args.backend or DEFAULT_BACKEND, args.provider, args.model, prompt, str(state.root))
        if session.get("status") != "ok":
            # A provider that refuses the call says nothing about the paper. This
            # branch used to fall through to an empty stdout, so a 403 on the
            # model arrived as "overview invalid after retries" and sent 26 good
            # candidates to the reject pile under a reason naming the wrong thing.
            model_failure = (
                session.get("reason")
                or f"rc={session.get('returncode')}: {(session.get('stderr') or '').strip()[-300:]}"
            )
            state.append_event("model_call_failed", attempt=attempt + 1, detail=model_failure)
            continue
        model_failure = ""
        output = extract_json(session.get("stdout") or "") or {}
        validation = validate_materials_output(output)
        if validation["valid"]:
            break
        state.append_event("materials_retry", attempt=attempt + 1, issues=validation["issues"])
    if model_failure:
        # Retryable: the paper is still a fine candidate once the provider answers.
        raise BlockedError("materials", f"model call failed: {model_failure}", retryable=True)
    if not validation["valid"]:
        raise BlockedError("materials", "overview invalid after retries: " + "; ".join(validation["issues"]))
    materials_dir = state.root / "stages" / "materials" / "assembled"
    assemble_materials(
        materials_dir,
        output,
        references_bib,
        template_tex,
        _render_agents_md(profile["agents_domain"]),
        state.root / "stages" / "materials" / "figures",
        tables_dir,
        None,
        table_inventory,
    )
    state.append_event("materials_assembled", paper=identifier, fingerprint=session.get("fingerprint"))

    # 3b. compile the ground-truth PDF in a copy of the source dir (figures + styles present)
    import shutil as _shutil

    # One scratch tree per paper, rebuilt from empty. A single shared directory
    # let paper N inherit paper N-1's main.aux, and a stale aux carrying another
    # document's \Newlabel entries aborts the compile with "Undefined control
    # sequence": six of seven tasks in a shard lost their ground-truth PDF to
    # exactly that, and the first paper passed only because it ran first.
    pdf_proof = state.root / "stages" / "conversion" / "pdf-proof" / slug
    if pdf_proof.exists():
        _shutil.rmtree(pdf_proof)
    _shutil.copytree(sources_dir, pdf_proof)
    pdf_result = latex.compile_ground_truth_pdf(main_tex_text, references_bib, pdf_proof, "main")
    ground_truth_pdf = pdf_result.get("pdf")
    if ground_truth_pdf is None:
        state.append_event("pdf_compile_failed", paper=identifier, log=pdf_result.get("log", "")[-800:])

    # 4. conversion: assemble the task tree
    task_dir = state.root / "tasks" / slug
    config = {
        "type": "experimental",
        "num_page": (metadata.get("year") or ""),
        "column": "1column",
        "conference": profile["conference"],
        "title": metadata.get("title") or identifier,
    }
    source_manifest = build_source_manifest(
        identifier, metadata, {"arxiv_source": fetched["sha256"], "sha256": fetched["sha256"]}
    )
    tree = build_task_tree(
        task_dir,
        identifier=identifier,
        domain_tag=profile["tag"],
        relevant_experience=profile["experience"],
        config=config,
        materials_dir=materials_dir,
        ground_truth_tex=main_tex_text,
        ground_truth_pdf=ground_truth_pdf,
        research_overview_long=output.get("overview_long") or "",
        source_manifest=source_manifest,
        texmf_dir=texmf_dir,
    )
    state.record_stage("conversion", {"status": "passed" if tree["valid"] else "blocked", "validation": tree})
    state.append_event("task_converted", paper=identifier, valid=tree["valid"])

    # 5. independent review gates
    review_model = args.review_model or args.model
    backend = args.backend or DEFAULT_BACKEND
    from .integrity import sha256_file

    def _tail(path: Path, n: int) -> str:
        return path.read_text(encoding="utf-8", errors="replace")[:n] if path.is_file() else ""

    file_inventory = sorted(str(p.relative_to(task_dir)) for p in task_dir.rglob("*") if p.is_file())
    gate_evidence = {
        "gate1": {
            "identifier": identifier,
            "title": metadata.get("title"),
            "authors": metadata.get("authors"),
            "doi": metadata.get("doi"),
            "year": metadata.get("year"),
            "license": metadata.get("license"),
            "source_sha256": fetched["sha256"],
            "main_tex": main_tex.name,
            "bib_file": [Path(b).name for b in probe["bib_files"]],
            "probe_issues": probe["issues"],
        },
        "gate2": {
            "identifier": identifier,
            "overview_short": (output.get("overview_short") or "")[:3000],
            "template_tex": template_tex[:3000],
            "references_sample": references_bib[:1500],
            "figures": figures,
            "tables": [t["id"] for t in table_inventory],
            "template_compiles": template_proof["ok"],
        },
        "gate3": {
            "identifier": identifier,
            "file_inventory": file_inventory,
            "task_toml": _tail(task_dir / "task.toml", 2000),
            "instruction": _tail(task_dir / "instruction.md", 3000),
            "test_state": _tail(task_dir / "tests" / "test_state.py", 3000),
            "oracle_sha256": sha256_file(task_dir / "solution" / "private" / "main.tex") if (task_dir / "solution" / "private" / "main.tex").is_file() else None,
            "main_pdf_bytes": (task_dir / "solution" / "private" / "main.pdf").stat().st_size if (task_dir / "solution" / "private" / "main.pdf").is_file() else None,
        },
    }
    gates: dict[str, dict] = {}
    for gate_name in ("gate1", "gate2", "gate3"):
        try:
            decision = run_gate(gate_name, gate_evidence[gate_name], backend, args.provider, review_model, str(state.root))
        except BlockedError as exc:
            decision = {"status": "blocked", "reason": exc.reason, "decision": None}
        gates[gate_name] = decision
        verdict = (decision.get("decision") or {}).get("decision") if decision.get("decision") else "blocked"
        state.record_stage(gate_name, {"status": verdict, "decisions": [decision]})
        state.append_event(f"{gate_name}_review", status=verdict, fingerprint=decision.get("fingerprint"))

    all_pass = all((gates[g].get("decision") or {}).get("decision") == "pass" for g in ("gate1", "gate2", "gate3"))

    # 6. acceptance request — always written; gates are recorded as evidence and the
    #    real Harbor oracle/nop trials are the authoritative acceptance gate.
    manifest = json.loads((task_dir / "manifest.json").read_text(encoding="utf-8")) if (task_dir / "manifest.json").is_file() else {}
    request = build_acceptance_request(identifier, task_dir, manifest, {"main_pdf": ground_truth_pdf is not None})
    write_acceptance_request(state.root / "acceptance" / f"{slug}-request.json", request)
    state.append_event("acceptance_requested", paper=identifier, gates_pass=all_pass)

    return {
        "paper": identifier,
        "task_dir": str(task_dir),
        "validation": tree,
        "gates": {g: (gates[g].get("decision") or {}).get("decision") if gates[g].get("decision") else "blocked" for g in ("gate1", "gate2", "gate3")},
        "acceptance_requested": True,
    }


def _render_agents_md(domain: str) -> str:
    from .contract import CANARY_GUID, render_template

    templates = Path(__file__).parent / "templates"
    return render_template(
        (templates / "AGENTS.md.j2").read_text(encoding="utf-8"),
        {"canary": CANARY_GUID, "domain": domain},
    )
