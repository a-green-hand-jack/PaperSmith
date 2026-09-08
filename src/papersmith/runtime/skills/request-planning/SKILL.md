---
name: request-planning
description: Clarify a scientific writing task request and resolve fixed or discovery selection without acquiring sources.
phase: parse-request
requires: []
tools: [parse_request]
outputs: [RequestSpec]
---

# Request Planning

Input: request text, explicit selection/identifiers, target count, output path,
authorized source roots/origins and execution/review backend/model references.
Paths below are relative to the runtime root, not this skill directory.

1. Clarify missing target and authorization. Explicit `--paper` locks identity;
   mentioning a paper in prose alone does not. Do not silently reinterpret a fixed
   request as discovery. Reject conflicting options or impossible count/selection.
2. With a trusted controller, call `parse_request` to validate positive integer
   count, explicit mode, canonical identifier syntax and model configuration.
3. Return a typed `RequestSpec` containing those fields and unresolved questions.
   Do not invent credentials, readable directories or available model entitlements.

`--describe` is deterministic parsing only: no model calls, source reads, network,
workspace creation or stage execution. Natural-language clarification here is
not an implementation of that CLI. Formal creation requires a trusted controller;
without it report the capability blocker and do not proceed. The controller must
reject a nonempty output directory and route existing runs to recovery.

No knowledge topic is required for parsing. Read only the selected parse-request
section of `workflows/create-task.md` when provided by the controller.
