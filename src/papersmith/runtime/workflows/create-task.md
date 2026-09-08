---
name: create-task
description: Create one or more auditable Harbor scientific writing tasks through proposal, three review gates and trusted acceptance.
phases: [parse-request, proposal, gate1, materials, gate2, conversion, gate3, acceptance, delivery]
---

# Create Task

This workflow is a controller contract, not a prompt that grants capabilities.
A trusted controller must supply the phase envelope, enforce role/tool/path
allowlists and write manifests. If it is absent, stop after clarification.

## Phase sequence

1. **parse-request** — apply `request-planning`; output `RequestSpec`. No source
   reads or model calls for describe-only parsing.
2. **proposal** — apply `source-acquisition`; acquire only authorized candidates
   and source evidence. Record proposal snapshot and hashes.
3. **gate1** — apply `scientific-review` with source-validation knowledge. Require
   an independent pass for each candidate; fixed rejection blocks substitution.
4. **materials** — apply `material-curation` to a frozen Gate 1 input.
5. **gate2** — independently review material accuracy, sufficiency, provenance,
   licensing and leakage. A rejection invalidates conversion for that snapshot.
6. **conversion** — apply `task-conversion` and freeze task/oracle manifests.
7. **gate3** — independently review task contract, public/private separation,
   rubric, oracle provenance and runnable entry points.
8. **acceptance** — apply `acceptance` via the trusted host worker. Require actual
   oracle=1 and nop=0, with immutable receipts matching all hashes.
9. **delivery** — controller writes `delivery.json` only after deterministic
   validation of count, uniqueness, gates, acceptance and evidence bindings.

Every phase writes a manifest and append-only events. Any failure blocks downstream
phases and records recovery. Never use model prose as a phase result. No phase
publishes externally; use `publish-release` only after explicit authorization.

## Failure and disclosure

The controller selects only the current phase's workflow section, skill and
knowledge topics. Ordinary writing sessions receive only instruction and public
materials. Private source records, validators, ground truth and oracle remain in
role-scoped storage. Credentials and raw sessions never enter evidence.

If any required tool, isolated reviewer, trusted worker, input hash or license
proof is unavailable, return `blocked` with the exact missing evidence. Do not
substitute a build, launcher startup, model statement or fabricated receipt.
