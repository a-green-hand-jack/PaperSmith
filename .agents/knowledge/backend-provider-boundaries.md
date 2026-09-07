# Backend and Provider Boundaries

PaperSmith supports OpenCode, Codex, and Claude Code as independent backends.
The runtime definition must not embed a provider key, auth store, model catalog,
or provider-specific execution loop. OpenCode accepts a runtime provider/model;
Codex and Claude Code use their own provider and model namespaces.

Docker E2E credentials must be supplied only by an explicit environment value
or read-only backend-specific mount. A successful image build is not product
behavior evidence.
