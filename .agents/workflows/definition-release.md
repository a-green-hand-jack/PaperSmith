# Definition and Release Workflow

1. Update the PaperSmith runtime definition without coupling it to a provider.
2. Run structural validation, consistency audit, and infrastructure health.
3. Run a real Docker E2E on the pi backend using only runtime-injected
   credentials, and record the provider/model actually used.
4. Build a fresh release archive and check that it excludes `.agents/`, every
   `AGENTS.md`, `development/`, credentials, and auth stores.
