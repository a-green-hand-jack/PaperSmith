# Capability Boundary

PaperSmith's approved scope is producing Harbor scientific writing tasks from
verified sources. This runtime currently supplies domain definitions only.

There is no implemented domain CLI, trusted phase controller, scoped backend
adapter, independent review runner or Harbor acceptance worker in this release.
The generic backend launcher does not enforce the production context and tool
allowlists. Do not start source processing, make review decisions or claim task
delivery through that launcher. Explain blockers and clarify the intended request.

A model response demonstrates only that a backend/provider interaction occurred.
An image build or binary startup is infrastructure-only evidence. Neither proves
source acquisition, isolation, recovery, three-gate review or Harbor acceptance.

Backends own execution, provider interaction and approvals. Providers and model
availability are injected at runtime, never embedded in the release. The future
controller must compose existing backend capabilities, not duplicate their loop.
