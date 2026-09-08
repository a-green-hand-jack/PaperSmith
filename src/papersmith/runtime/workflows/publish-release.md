---
name: publish-release
description: Publish an explicitly authorized, validated immutable delivery without leaking private runtime data.
phases: [publish]
---

# Publish Release

Entry: explicit authorization naming target registry/audience and artifacts; local
delivery passes fresh deterministic validation; redistribution rights verified.
Knowledge: `review-integrity` and `task-contract`. No model skill may grant publish
permission. Tools: `validate_delivery`, `inspect_release`, `publish_artifact`,
`verify_publication` through a trusted publisher, not an unrestricted shell.

1. Revalidate delivery and source/material redistribution constraints. Distinguish
   tool release, task dataset, private source archive and evaluation evidence;
   authorize and version each separately.
2. Inspect an explicit export allowlist. Tool payload contains only reviewed runtime
   files and excludes every `AGENTS.md`, development resources, credentials, raw
   sessions, user data and run workspaces. Task artifacts require a registry that
   preserves solver isolation for private validators/ground truth and solutions;
   never publish a producer workspace or private source archive by default.
3. Bind immutable source revision, artifact hashes, actual E2E image/backend/model
   metadata, task hashes and trusted acceptance receipts. Check no secret values or
   raw session content are included in metadata.
4. Publish only to the authorized target, then verify the remote digest/version.
   Return publication receipt and immutable artifact reference separately from
   local `delivery.json`; do not rewrite acceptance history.

Missing permission, license evidence, validation, trusted publisher or remote digest
match blocks publication. A failed upload does not invalidate local delivery, but
is not publication success. Retrying requires matching immutable artifact and target;
changed content requires a new version and revalidation. Never publish implicitly.
