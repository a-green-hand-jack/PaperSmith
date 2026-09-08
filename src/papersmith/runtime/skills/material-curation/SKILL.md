---
name: material-curation
description: Curate scientifically grounded public writing materials with private provenance bindings.
phase: materials
requires: [material-schema]
tools: [read_source_evidence, extract_materials, validate_materials, export_public_materials]
outputs: [MaterialRecord, MaterialManifest]
---

# Material Curation

Input: immutable proposal and verified Gate 1 pass for the same hashes.
Runtime-root reference: `knowledge/material-schema.md`.

1. Require the authorized curation role; access only the minimum selected source
   evidence with `read_source_evidence`. This is not the ordinary writing role.
2. Organize methods, setup, results, figures/tables, citations and limitations using
   `extract_materials`. Preserve units, uncertainty and source anchors.
3. Use `validate_materials` to check schema, references and numeric consistency.
4. Export only explicitly approved public records with `export_public_materials`;
   keep private source mappings separate. Return hashes and the material manifest.

Do not invent missing results, citations or permission. Insufficient source data,
provenance or export isolation blocks the phase. Do not copy the source workspace,
original paper prose, ground truth or oracle into public materials. Gate 2 is a
separate independent review, not the curator's self-assessment.
