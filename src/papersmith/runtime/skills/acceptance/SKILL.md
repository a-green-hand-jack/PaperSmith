---
name: acceptance
description: Request real Harbor oracle and nop trials through a trusted host worker and verify their receipts.
phase: acceptance
requires: [task-contract]
tools: [request_acceptance, read_acceptance_receipt, verify_acceptance]
outputs: [AcceptanceReceipt]
---

# Acceptance

Input: frozen task/validator/image/implementation hashes and all three matching gate
passes. Runtime-root reference: `knowledge/task-contract.md`.

1. Require a configured trusted host acceptance worker. No Docker socket, host shell
   or private credentials may be exposed to the producer/writer model.
2. `request_acceptance` submits a hash-bound request for actual Harbor oracle/nop
   trials. Record worker identity, Harbor version and request fingerprint.
3. `read_acceptance_receipt` reads immutable worker-issued results; do not write or
   edit receipts. `verify_acceptance` checks origin, hashes, statuses and rewards.
4. Only actual successful oracle=1 and nop=0 for each task satisfy acceptance.
   Return verified references to the controller for deterministic delivery checks.

Missing worker, forged/untrusted receipts, stale hashes, timeout, failed tools or
missing scores are blocked, not successful trials. A failed nop invocation is not
proof of nop=0. Keep trial evidence and report the failing component for recovery.
Never substitute a model assessment, compiled template or successful image build.
