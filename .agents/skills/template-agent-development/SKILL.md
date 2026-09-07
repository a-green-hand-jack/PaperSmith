---
name: template-agent-development
description: Use when creating, synchronizing, or migrating a coding-agent repository with this template's independent scaffold, backend, and LLM layers.
metadata:
  short-description: Build and maintain agents from the coding-agent template
---

# PaperSmith Template Development

Use this development-only skill when selectively synchronizing PaperSmith with
its configured template upstream. Follow [sync-template.md](references/sync-template.md).

Keep `src/papersmith/runtime/`, PaperSmith development resources, and product
documentation downstream-owned. Do not copy upstream `.agents/`, registry,
benchmarks, release evidence, credentials, or development instructions. Keep
the scaffold, coding-agent backend, and runtime provider/model independent.

Real provider-backed Docker E2E is required before claiming Agent behavior.
