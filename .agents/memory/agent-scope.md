# PaperSmith Initialization Decision

PaperSmith currently has no finalized domain behavior. It is an installable,
provider-neutral scaffold that must not imply product capabilities before a
product scope is approved.

The supported execution backend is pi and only pi (decided 2026-09-09;
`@earendil-works/pi-coding-agent`). `runtime/package.json` is the runtime
manifest. Provider availability and model entitlement are runtime concerns
rather than properties embedded in the PaperSmith release.

Retired: this record previously declared three separate execution backends as
supported. That multi-backend scope is superseded by the pi-only decision above
and must not be reintroduced as a requirement. The retired backend names are
deliberately not repeated here; `scripts/check-pi-only-backend.py` is the gate
that keeps them out of the repository.
