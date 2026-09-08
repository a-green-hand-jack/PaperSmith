---
name: agent-infrastructure-health
description: Verify PaperSmith installer, launcher, Docker runtime, and product boundary without provider credentials.
---

# PaperSmith Infrastructure Health

Use this check after changing launcher, installer, Docker, backend selection, or
runtime packaging:

```bash
python3 .agents/skills/agent-infrastructure-health/scripts/check_infrastructure.py \
  --agent papersmith
```

It builds a clean image and verifies the `pi` binary, the installed
`agent-definition/package.json` manifest, every command the runtime tools
declare in `runtime/tools/pyproject.toml`, the `uv` prerequisite, plus the
installed command and payload boundary. Pass `--skip-build` only when a
known-good image was built from the current worktree.

It is infrastructure-only; a real provider-backed Docker E2E on the pi backend
remains mandatory before claiming Agent behavior.
