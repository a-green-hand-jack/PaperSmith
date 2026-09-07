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

It builds a clean image and verifies the three backend binaries plus the
installed command and payload boundary. It is infrastructure-only; real Docker
E2E remains mandatory for OpenCode, Codex, and Claude Code.
