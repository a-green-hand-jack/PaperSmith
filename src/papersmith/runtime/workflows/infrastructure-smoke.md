# Infrastructure Smoke Workflow

1. Load the `runtime-smoke` skill.
2. Inspect only the supplied workspace and the installed product behavior.
3. Verify the installed `papersmith-tool --check` tool before writing the artifact.
4. Create and verify `artifacts/papersmith-smoke.md`.
5. Return a concise result that names the verified artifact.

Workflow sentinel: `PAPERSMITH_WORKFLOW_OK`.
