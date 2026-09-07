# PaperSmith

PaperSmith is an initialized, backend-neutral coding-agent scaffold. Its
product runtime is self-contained under `src/papersmith/runtime/`; OpenCode,
Codex, and Claude Code remain interchangeable execution backends.

```text
PaperSmith runtime -> coding-agent backend -> runtime-selected provider/model
```

Product-specific behavior has not been defined yet. Provider models and
credentials are selected only at runtime.

## Development checks

```bash
./scripts/validate-definition.sh papersmith
python3 .agents/skills/agent-consistency-audit/scripts/audit_agent.py --agent papersmith --strict
python3 .agents/skills/agent-infrastructure-health/scripts/check_infrastructure.py --agent papersmith
```

The last command is infrastructure-only. Before claiming behavior, run a real
Docker E2E for each supported backend with a provider credential injected by an
explicit environment value or read-only backend-specific mount.

## Product boundary

Release archives and final images contain the runtime definition, launcher, and
selected backend CLIs. They exclude development resources, every `AGENTS.md`,
credentials, auth stores, and raw provider sessions.
