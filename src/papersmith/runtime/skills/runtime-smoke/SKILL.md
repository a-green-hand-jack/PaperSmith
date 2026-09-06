---
name: runtime-smoke
description: Validate an installed PaperSmith runtime by inspecting the workspace and writing a checked smoke artifact.
---

# Runtime Smoke

Use this skill when the user asks for an infrastructure or installation smoke
test.

1. Inspect the current workspace without reading credentials or environment
   files.
2. Confirm that the workspace is separate from the Agent definition directory.
3. Run `papersmith-tool --check` and verify the exact output `PAPERSMITH_TOOL_OK`.
4. Write `artifacts/papersmith-smoke.md` containing the exact headings
   `Product runtime`, `Workspace access`, and `Skill loaded`.
5. Re-read the artifact and verify all three headings are present.
6. Include `PAPERSMITH_KNOWLEDGE_OK` and `PAPERSMITH_TOOL_OK` under the Product runtime section and
   `PAPERSMITH_WORKFLOW_OK` under the Workspace access section.
7. Report only the checked artifact path and outcome; do not include raw
   provider output or secret values.
