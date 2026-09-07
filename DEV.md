# PaperSmith Development Guide

PaperSmith is maintained as three independent layers:

```text
PaperSmith runtime -> OpenCode/Codex/Claude Code -> provider/model
```

Develop product behavior with the runtime identity, knowledge, skills, and
workflows in `src/papersmith/runtime/`. Do not implement an execution loop,
model client, approval system, or parallel tool loop already supplied by the
selected coding-agent backend.

All three backends are supported. OpenCode provider/model selection uses its
runtime namespace; Codex and Claude Code retain their own credentials and model
namespaces. Never embed a provider catalog or credential in the scaffold.

Run the definition, consistency, infrastructure, and real provider-backed
Docker E2E gates described in `README.md`. A Docker build or backend version
check alone is not Agent behavior evidence.
