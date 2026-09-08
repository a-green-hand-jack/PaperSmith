---
name: runtime-smoke
description: Validate an installed PaperSmith runtime by inspecting the workspace and writing a checked smoke artifact.
---

# Runtime Smoke

Infrastructure probe retained for runtime smoke validation; not product behavior.

Use this skill when the user asks for an infrastructure or installation smoke
test.

1. Inspect the current workspace without reading credentials or environment
   files.
2. Run `pwd` and list the workspace directory to confirm you are inside the
   supplied workspace. Do not read or glob the Agent definition directory or
   any path outside the workspace; your runtime content is already injected
   into context.
3. Run `papersmith-tool --check` and verify the exact output `PAPERSMITH_TOOL_OK`.
4. Write `artifacts/papersmith-smoke.md` containing the exact headings
   `Product runtime`, `Workspace access`, and `Skill loaded`.
5. Under `Product runtime`, include `PAPERSMITH_KNOWLEDGE_OK` and
   `PAPERSMITH_TOOL_OK`.
6. Under `Workspace access`, include `PAPERSMITH_WORKFLOW_OK`.
7. Under `Skill loaded`, include the skill name `runtime-smoke`.
8. Re-read the artifact and verify all three headings and sentinels are present.
9. Report only the checked artifact path and outcome; do not include raw
   provider output or secret values.
