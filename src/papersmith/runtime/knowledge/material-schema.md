# Material Schema

A public `MaterialRecord` has a stable ID, type, content/artifact path, units and
uncertainty where relevant, and a provenance reference ID. Its private provenance
map binds that ID to source hash, exact anchor, extraction/transform tool version
and reviewer evidence. Do not leak private paths or source answer text through
public provenance references.

Required types cover research question, method, experimental setup, results,
figures/tables, citations and limitations. Record unavailable types explicitly;
material sufficiency is a review decision, not permission to invent missing data.

- Methods: hypotheses, assumptions, procedures and settings; distinguish reported
  choices from inferred choices. Unverified inference cannot become a supplied fact.
- Results: values, units, labels, sample sizes, baselines and uncertainty actually
  present in the source. Never interpolate missing experiments or claim causality
  from correlation. Maintain a checked mapping for every numeric transformation.
- Figures/tables: bind each label, legend, axis and datum to evidence; ensure
  readability and licensing. Do not silently alter values to fit a narrative.
- Citations: verifiable bibliographic entries and claim-to-reference bindings;
  absence of a reference must not be filled by a plausible fabricated citation.
- Limitations: separate source-reported limitations from supported reviewer
  observations; do not invent negative findings.

Gate 2 checks scientific consistency, sufficiency for the requested writing task,
provenance coverage, units, citations, licensing and leakage. Public materials must
be an explicit allowlisted export, not a recursive copy of the source workspace.
Do not include source prose that supplies the answer, private records, validators
or oracle content. Scientific facts can be shared; private reference answers cannot.

The synthetic oracle is written anew using only the frozen public materials and
instruction, in an isolated role. The original paper cannot substitute for it.
