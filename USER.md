# PaperSmith User Guide

`papersmith` is an initialized coding-agent scaffold. Product-specific behavior
has not been defined yet; use it only with an explicit task and selected
backend/provider runtime.

## Backends and models

The installed command supports OpenCode, Codex, and Claude Code:

```bash
papersmith --backend opencode --provider <provider> --model <model> "Review this abstract"
papersmith --backend codex --model <model> "Improve this outline"
papersmith --backend claude --model <model> "Identify evidence gaps"
```

Provider/model availability is determined by the selected backend and your
runtime account. Supply credentials only through that backend's standard
runtime mechanism; never put keys, auth stores, or `.env` files in a PaperSmith
release or repository.
