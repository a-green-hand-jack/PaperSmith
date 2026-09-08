# PaperSmith Control Package

Development-only guidance. This package is the deterministic control layer for
the PaperSmith Agent. Keep it a typed, evidence-first controller: state
transitions require validated hashes and tool results, never natural-language
claims. Do not add a model client, session manager, approval loop, or shell/
Docker escape here; those belong to the selected backend or a trusted host
worker. No credentials, raw sessions, or private user data in this directory.
