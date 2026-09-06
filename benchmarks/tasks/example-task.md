# PaperSmith Infrastructure Smoke Task

Use the `runtime-smoke` skill to validate this installed Agent. Inspect the
supplied workspace without reading credentials or environment files. Run
`papersmith-tool --check` and verify `PAPERSMITH_TOOL_OK`. Write
`artifacts/papersmith-smoke.md` with the headings `Product runtime`, `Workspace
access`, and `Skill loaded`, then re-read it and report the checked path. Do
not include secrets or raw provider output. Include the exact sentinels
`PAPERSMITH_KNOWLEDGE_OK`, `PAPERSMITH_TOOL_OK`, and `PAPERSMITH_WORKFLOW_OK` in the
corresponding artifact sections to prove the runtime knowledge, tool
environment, and workflow instructions were loaded.
