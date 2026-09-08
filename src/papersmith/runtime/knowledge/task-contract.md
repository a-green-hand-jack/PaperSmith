# Harbor Task Contract

A task contains `instruction.md`, `task.toml`, `manifest.json`, public
`environment/materials/`, private `tests/private/ground_truth/`, and a synthetic
`solution/`. Conversion must also supply the environment build definition and
verifier/solution entry points required by the installed, pinned Harbor version;
the directory skeleton alone is not a runnable task.

The instruction specifies the scientific writing objective, allowed materials,
submission paths/formats, compilation requirements and an explicit scoring rubric.
Submission artifacts and build commands must agree across instruction, environment,
verifier and oracle. Verify paths, dependency availability and tool versions.

Ordinary writing Agents see only instruction and public materials. Private ground
truth, original PDF/TeX, verifier implementation and oracle must not enter the
agent image, mounts or context. Validate actual build contexts and mounted paths,
not just directory names. Submissions are untrusted: verify in a sandbox with
resource limits and no unrestricted shell escape, network or host access.

The oracle is a newly written response to the public task, not copied source prose.
Its writing session cannot access private references. The deterministic renderer
and trusted verifier may assemble private task components without exposing them
to that session. Gate 3 checks the frozen task, rubric, private/public separation,
reference provenance and runnable entry points in an independent review session.

Acceptance runs through a trusted host worker, never by giving the producer or
writer Docker socket access. Request binds task tree, public/private manifests,
validator, image digest, implementation, Harbor version and gate hashes. Worker
runs real oracle and nop trials, returns immutable/read-only receipts with trial
IDs, exit status, reward and artifact hashes. Require oracle=1 and nop=0 for every
task; timeout, missing reward or tool failure is blocked, not a score of zero.

`delivery.json` binds requested count, unique task IDs and all these evidence
hashes. Validate every task and gate against current files. Changed inputs invalidate
acceptance. A hash checks content consistency, not issuer authority: receipt origin
must also be authenticated by the trusted worker channel. Do not invent signatures,
trust a model-authored receipt or publish automatically after local delivery.
