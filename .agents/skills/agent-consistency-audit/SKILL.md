---
name: agent-consistency-audit
description: Audit PaperSmith definition consistency, product boundaries, and release contents without reading credentials.
---

# PaperSmith Consistency Audit

Run this deterministic preflight after a substantial definition or packaging
change and before release:

```bash
python3 .agents/skills/agent-consistency-audit/scripts/audit_agent.py \
  --agent papersmith --strict
```

The audit checks the selected manifest, runtime structure and JSON, product
skill frontmatter, obvious credential-like runtime paths, shell/Python syntax,
and optionally a release archive. It is not provider-backed behavior evidence;
run the Docker E2E separately for every supported backend.
