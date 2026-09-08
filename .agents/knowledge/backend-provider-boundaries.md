# Backend and Provider Boundaries

The PaperSmith scaffold supports pi and only pi as its execution backend,
installed as `@earendil-works/pi-coding-agent`. `runtime/package.json` is the
runtime manifest and its `agent` section declares `backend: pi`.

Provider and model are runtime-injected, never scaffold properties. The runtime
definition must not embed a provider key, auth store, model catalog, or
provider-specific execution loop, and the implementation must stay LLM-agnostic:
no prompt, tool, or skill may assume a particular provider or model family.

Three layers stay independent:

1. Agent scaffold - PaperSmith's identity, knowledge, skills, workflows, tools.
2. pi backend - loads those resources and runs the execution loop.
3. LLM provider/model - selected at run time, outside the release.

Docker E2E credentials must be supplied only by an explicit environment value
or read-only auth mount. A successful image build is not product behavior
evidence.
