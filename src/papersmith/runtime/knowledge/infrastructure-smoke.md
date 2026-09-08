# Infrastructure Smoke Knowledge

Infrastructure probe retained for runtime smoke validation; not product behavior.

A valid smoke run demonstrates that the installed product can load its runtime
definition, use a project workspace, load a product skill, write an artifact,
and report a checked result. The runtime owns a minimal uv-managed tool
environment so a skill can verify a real tool invocation. Development-agent
instructions and provider credentials are never product inputs.

Infrastructure smoke sentinel: `PAPERSMITH_KNOWLEDGE_OK`.
