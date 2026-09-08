# Knowledge Index

This is the only always-loaded domain index. Paths are relative to the runtime
root. A trusted controller selects topics for a phase; this index does not grant
filesystem or network permission. Do not load all listed documents.

| Topic | Trigger | Phases | Path |
| --- | --- | --- | --- |
| Capability boundary | Missing implementation or execution envelope | clarification | `knowledge/initialization-boundary.md` |
| Source validation | Resolve a paper, fetch or audit source evidence | proposal, gate1 | `knowledge/source-validation.md` |
| Material schema | Curate or review public scientific materials | materials, gate2, conversion | `knowledge/material-schema.md` |
| Task contract | Convert, comprehensively review or accept a Harbor task | conversion, gate3, acceptance, delivery | `knowledge/task-contract.md` |
| Review integrity | Audit a gate, reuse evidence, validate or publish | gate1, gate2, gate3, resume, validate, publish | `knowledge/review-integrity.md` |

Request planning uses explicit request fields, without opening paper materials.
A workflow may require more than one topic; only its selected current-phase
section belongs in the model context. Selection, hashes and tool allowlists must
be recorded in the phase manifest. Tools return evidence paths, not blanket read
access. Ordinary writing sessions receive only the task instruction and approved
public materials, never this producer's private workspace.
