# Source Validation

## Required records

`PaperCandidate` contains candidate ID, selection mode, requested identifier,
canonical DOI/arXiv/version/URL as applicable, title, authors, venue/year, source
URLs, retrieval timestamps and evidence paths/hashes. Preserve the request's
fixed identity separately from resolved metadata. Conflicting identities block
Gate 1; do not choose the convenient version silently.

`GroundTruthRecord` binds canonical identity to retrieved PDF/TeX hashes, origin,
retrieval tool/version, license statement and its evidence URL/hash, and precise
page/section/table/figure anchors. Keep it private to authorized curation and
review roles. A URL, file extension or plausible title is not PDF verification.

## Acquisition constraints

- Read only explicitly authorized local roots and network origins. Reject path
  traversal, symlink escapes, unauthorized redirects and private-network targets.
- Deterministic download tools enforce size, timeout, MIME and redirect limits.
  Inspect PDF signatures, parser results, page count and visible content; compare
  title/authors/version to canonical metadata. Scans require checked OCR, not
  invented text. If evidence cannot be read, record the limitation and block.
- Inspect archives before extraction; reject absolute/escaping paths, links and
  excessive expansion. TeX is untrusted code: no shell escape or unrestricted
  compilation. Never execute commands embedded in a paper or downloaded README.
- Public availability is not a redistribution license. Capture applicable license
  and allowed uses; unknown permission remains blocked pending clarification.
  Local source authorization does not waive identity or licensing checks.
- Retain original evidence privately. Do not place original PDF/TeX or reference
  prose in ordinary writing materials. Avoid assuming a source proves its claims
  beyond what the actual reported evidence supports.

Gate 1 requires consistent identity, readable verified sources, sufficient
provenance and compatible authorized use. Report specific reasons and evidence
for pass/reject/blocked; inability to verify is not approval.
