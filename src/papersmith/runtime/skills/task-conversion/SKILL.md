---
name: task-conversion
description: Assemble a Harbor writing task and a freshly written public-material-only oracle.
phase: conversion
requires: [material-schema, task-contract]
tools: [render_task, write_reference, validate_task, compile_reference]
outputs: [TaskManifest, OracleManifest]
---

# Task Conversion

Input: frozen public materials, private provenance handles, same-input Gate 1/2
passes and explicit task/output contract. References relative to runtime root:
`knowledge/material-schema.md` and `knowledge/task-contract.md`.

1. Require enforced separation between deterministic assembly, private verification
   and the oracle-writing role. Do not pass private handles' contents to the writer.
2. `render_task` assembles instruction, pinned Harbor configuration, environment,
   templates and a verifier matching the published submission/rubric contract.
3. `write_reference` requests a fresh isolated writing session using only instruction
   and frozen public materials. It must not copy the original source paper.
4. `compile_reference` runs constrained compilation with no shell escape and checks
   actual outputs. `validate_task` checks entry points, manifests and leakage.
5. Return task/oracle hashes for independent Gate 3; do not claim acceptance.

Unimplemented tool interfaces, missing dependencies, material insufficiency,
compilation failure or leakage block conversion. Do not relax the rubric to make
an oracle pass, insert known-answer shortcuts or give the writer private evidence.
