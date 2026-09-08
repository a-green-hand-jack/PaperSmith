---
name: resume-run
description: Resume a run only when input, implementation, context and dependency fingerprints justify reuse.
phases: [resume]
---

# Resume Run

Entry: explicit existing run path; trusted controller available; exclusive write
lock acquired. Skill: `recovery`. Knowledge: `review-integrity`. Tools limited to
`inspect_run`, `verify_stage`, `plan_resume` until the controller schedules a phase.

Read `run.json`, append-only events and manifests. Verify every reused stage's
inputs, outputs, context/implementation/tool policy and dependency fingerprints.
Output a `ResumePlan` listing reusable, incomplete, failed and invalidated stages
with reasons. Preserve attempts and mark stale downstream decisions and receipts.

Gate: only fully verified passed stages are reusable. Fail closed on missing or
untrusted evidence. A new target count means total tasks. Do not mutate fixed
identities or the original request; contradictory requests require a new run.

Next: controller selects the earliest required production phase per task, using
`create-task.md` and a new role-scoped session. Revalidate final delivery after
reruns. Never delete failures, manually repair hashes or bypass gates. No controller
means no resume execution, even when general backend filesystem tools exist.
