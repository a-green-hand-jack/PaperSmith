# Memory Policy

Do not retain user memory or build a user profile across tasks. Keep current-run
state and evidence only in the explicitly authorized run workspace. Do not use
backend conversation history as authoritative state.

The controlled workspace contains `run.json`, append-only `events.jsonl`, `inputs/`,
`stages/`, `acceptance/`, `tasks/` and `delivery.json`. The controller, not the model,
writes state and manifests after validating tool results. Record input/output
hashes, implementation/context fingerprints, dependency fingerprints, review
results, failure reasons, recovery suggestions and sanitized tool evidence.
Store opaque model session IDs and response fingerprints, never raw provider
sessions. Avoid identifiers containing tokens or credentials.

Credentials, authentication stores and private user data must not be copied to
runtime definitions, Git, event logs, manifests or model summaries. Authorized
research artifacts belong only in the role-scoped run storage. Keep private
source evidence and oracle material separate from public task materials.

Retain failed attempts and rejection evidence. Do not delete or overwrite evidence
to make a run appear successful. Resume requires verified hashes and dependencies;
a remembered result or a previous model statement is not reusable evidence.
Do not access another run unless explicitly authorized for that request.
