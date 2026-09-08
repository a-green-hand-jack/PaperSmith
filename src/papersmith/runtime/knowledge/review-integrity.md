# Review and Evidence Integrity

Each gate runs in a fresh, independently scoped reviewer session, not the producer
conversation. A new role label in the same conversation is insufficient. Record
reviewer backend/model, opaque session ID, response fingerprint and exact reviewed
input/context hashes. Backend availability alone does not establish isolation.

`ReviewDecision` contains gate ID, candidate/task ID, input hashes, criterion-level
findings with evidence references, decision (`pass`, `reject`, `blocked`), reasons
and recovery suggestions. Tools validate structure and evidence bindings before
state changes. Empty findings, mismatched inputs, missing sessions or unverified
claims cannot pass. Failed review remains visible even after a later successful run.

Gate 1 checks identity, source readability, provenance and authorized use. Gate 2
checks material accuracy, completeness, scientific consistency and leakage. Gate 3
checks the assembled task, rubric, oracle provenance and execution/isolation
contract. Reviewers receive only the minimal read-only evidence for their gate;
private references must never be forwarded to the ordinary writing session.

Every stage manifest records input snapshot hashes, implementation fingerprint,
selected workflow/skill/knowledge hashes, role and tool policy, tool results,
output hashes, upstream fingerprints and review/failure details. Hash deterministic
file bytes with SHA-256 and canonical manifests; reject escaping paths, symlinks,
duplicate entries and unexpected files. Validate all referenced evidence.

The controller exclusively holds the run write lock; events are append-only and
stage results are committed atomically. Crash/incomplete output is not a passed
stage. Reuse requires all inputs, outputs, context, implementation and dependencies
to match, plus a valid previous decision. Invalidate changed stages and downstream
consumers. Never repair hashes by hand or discard failed attempts.

Validation is deterministic and read-only: check counts, structure, three gates,
actual trusted oracle/nop receipts and all bindings without calling models. Missing
or untrusted evidence blocks delivery. Publication requires explicit authorization,
valid local delivery, immutable version/digest binding and redistribution checks.
