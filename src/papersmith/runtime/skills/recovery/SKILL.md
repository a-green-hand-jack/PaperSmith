---
name: recovery
description: Determine reusable and invalidated stages from verified run evidence without erasing failures.
phase: resume
requires: [review-integrity]
tools: [inspect_run, verify_stage, plan_resume]
outputs: [ResumePlan]
---

# Recovery

Input: explicitly authorized existing run path and optional new total target count.
Runtime-root reference: `knowledge/review-integrity.md`.

1. Controller acquires the exclusive run lock before any modification. Use
   `inspect_run` for state/manifests, never raw provider history or another run.
2. `verify_stage` compares inputs, outputs, context selections, implementation,
   tool policy and dependency fingerprints against recorded passed stages.
3. `plan_resume` marks failed, incomplete or mismatching stages and downstream
   consumers for rerun. Retain independent valid task chains where safe.
4. Return the plan and reasons; only the controller schedules production stages
   with their original role isolation and independent reviews.

A new count is a total, not an increment. Increasing discovery count may add new
candidates without replacing valid tasks. Conflicting fixed identities or attempts
to rewrite the original request require a new request, not silent mutation.

Missing evidence, invalid paths or tampering block reuse. Do not repair hashes by
hand, erase failures, reset rejection history or accept stale worker receipts.
If the controller is absent, explain the blocker rather than implementing resume
by editing files with general backend tools.
