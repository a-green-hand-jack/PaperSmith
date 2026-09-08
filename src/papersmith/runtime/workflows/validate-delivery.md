---
name: validate-delivery
description: Validate task delivery deterministically without model calls or task regeneration.
phases: [validate]
---

# Validate Delivery

Entry: explicitly authorized run with `delivery.json`; deterministic validator
available. Knowledge: `review-integrity` and `task-contract`, interpreted by the
validator, not loaded into a model session. No model skill invocation is required;
acceptance evidence follows the `acceptance` skill's contract. Tools:
`validate_delivery` (read-only).

Check requested count and unique task IDs; required files and real Harbor entry
points; current tree/manifests/implementation/image/validator hashes; three
independent same-input review passes; authentic worker receipts with successful
oracle=1 and nop=0 per task; and all dependency/evidence bindings. Reject missing,
escaping, symlinked, stale, unexpected or untrusted artifacts.

Output: structured validation report containing valid/blocked status, checked
hashes, task paths and exact failed checks. Success exits zero; any failed check
exits nonzero. Do not generate tasks, call a provider, rerun trials, modify evidence
or repair hashes. Validation is not a production run or publication authorization.

Next: report valid delivery or route user-authorized recovery to `resume-run.md`.
No cached validation is reusable after a bound artifact or policy changes.
