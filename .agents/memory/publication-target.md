# Publication Target

PaperSmith delivery tasks are published to the Hugging Face dataset
`Jack-Jieke-Wu/Paper-Writing-Exam`, NOT to Harbor. Harbor `auth login` is not
used for publication.

- Decision date: 2026-09-07 (user instruction).
- Dataset id: `Jack-Jieke-Wu/Paper-Writing-Exam` (owner `Jack-Jieke-Wu`,
  `hf auth whoami`).
- Upload with `hf upload Jack-Jieke-Wu/Paper-Writing-Exam <dir> --type dataset`.

## Correct layout (must match the existing benchmark)

This dataset is an immutable Harbor benchmark release (`v0.4.1`, 274 tasks)
with per-configuration task trees. Do NOT add root-level `data/` or `tasks/`;
that layout is wrong and was reverted 2026-09-07.

- Task trees live under a configuration directory, e.g.
  `lifesci-paperrecon-short/lspr-0023/`.
- Config dirs: `paperwrite-bench-short/pwb-*`, `paperwritingbench-sparse-plotoff/*`,
  `lifesci-paperrecon-short/lspr-*`, `hello-world/`.
- Each task dir matches the Harbor paper-reconstruction layout:
  `task.toml` (schema 1.4), `instruction.md`,
  `environment/{Dockerfile, materials/{research_overview.md, references.bib,
  template.tex, figures/, tables/, code/, *_summary.txt}, texmf/}`,
  `solution/{solve.sh, normalize.py, private/{main.tex, main.pdf, config.yaml}}`,
  `tests/{Dockerfile, test.sh, test_state.py, grader_*.py, private/..., texmf/, vendor/}`.
- Config level carries `dataset-manifest.jsonl` mapping task_id ->
  upstream_paper_id + upstream_revision.

## Construction source

`lifesci-paperrecon-short` is the PaperSmith construction from licensed
LifeSci arXiv `q-bio` papers. The construction pipeline lives in
`github.com/a-green-hand-jack/paperbench-harbor` (`src/paperbench_harbor`,
`paperbench-distribute build-lifesci-paperrecon-source`; docs:
`docs/lifesci-paperrecon-construction.md`). Reuse that pipeline; do not
reimplement paper-specific LaTeX/figure/table surgery in PaperSmith.

## Rules

- After upload, the user reviews on huggingface.co.
- Never expose verifier-private files (ground truth, rubric, citation labels)
  to the writer; benchmark data must never appear in training corpora.
- Record the dataset repo + immutable revision + configuration + task id for
  any reported result.
