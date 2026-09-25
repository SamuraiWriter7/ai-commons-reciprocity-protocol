# Changelog

This document records the staged development of
ai-commons-reciprocity-protocol.

Project versions and individual record schema versions are managed
separately. Version headings describe development milestones and
do not imply that corresponding Git tags or releases exist.

## v0.5 — Integration conformance

### Added

- Shared-evidence example demonstrating that two accepted receipts
  may reference the same report while allocating adjacent,
  non-overlapping quantities:
  `examples/pass/fulfillment-receipt-shared-evidence.example.json`.
- Overlapping allocation rejection example:
  `examples/fail/fulfillment-receipt-overlapping-slices.example.json`.
- Inconsistent metadata rejection example for records sharing
  a delivery ID:
  `examples/fail/fulfillment-receipt-inconsistent-delivery.example.json`.
- Accepted quantity exceeding the commitment quantity rejection example:
  `examples/fail/fulfillment-receipt-accepted-quantity-exceeded.example.json`.
- Cross-commitment double-allocation rejection example:
  `examples/fail/fulfillment-receipt-cross-commitment-overlap.example.json`.
- Integrated requirements, example expectations, and verification
  boundaries in `specs/conformance.md`.

### Changed

- Registered five additional datasets in
  `scripts/validate_examples.py`, bringing the suite to 14 examples.
- Added complete expected-summary comparison for the shared-evidence
  example: 100 hours promised, 100 accepted, zero remaining,
  and status `fulfilled`.
- Retained complete expected-summary comparison for the partial
  fulfillment example: 100 hours promised, 40 accepted,
  60 remaining, and status `partial`.
- Added a suite assertion that invalid datasets produce no
  fulfillment summaries.
- Updated `README.md` to describe the four-record model,
  validation workflow, versioning, and verification boundaries.

### Clarified

- Evidence reuse is permitted; duplicate allocation of the same
  delivery quantity is prohibited.
- Allocation overlap checks apply across commitments within the
  supplied dataset.
- All confirmation statuses reserve their allocated slices.
- Records sharing a delivery ID must contain identical delivery
  metadata, regardless of object property order.
- Separate dataset validations do not establish consistency
  across submissions.
- Validation of record consistency does not authenticate evidence
  or establish real-world performance.
- Receipt replacement, revocation, and status transitions remain
  undefined in v0.5.

### Validation

- Registered suite: five valid and nine deliberately invalid datasets.
- GitHub Actions passed all 14 registered examples.
- Invalid examples pass the suite only when their error-code sets
  exactly match the expected sets.
- Passing the registered suite does not constitute exhaustive testing.

### Compatibility

- No new record type or schema was introduced.
- Existing schema versions remain unchanged:
  - `schemas/reciprocity-agreement.schema.json`: `0.1.0`
  - `schemas/agreement-acceptance.schema.json`: `0.2.0`
  - `schemas/return-commitment.schema.json`: `0.3.0`
  - `schemas/fulfillment-receipt.schema.json`: `0.4.0`
- Existing records do not need to change their `schema_version`
  solely because the project reached v0.5.

## v0.4 — Fulfillment receipts

### Added

- `schemas/fulfillment-receipt.schema.json` with schema version `0.4.0`.
- Fulfillment requirements in `specs/fulfillment-receipt.md`.
- Delivery identity, resource, unit, quantity, timestamp, and
  source-record references.
- Allocation slices defined by `slice_start` and `quantity`.
- Confirmation statuses:
  `pending`, `accepted`, `rejected`, and `disputed`.
- Beneficiary confirmation with authority and evidence references.
- Required reasons for rejected and disputed confirmations.
- Partial fulfillment example:
  `examples/pass/fulfillment-receipt-partial.example.json`.
- Incorrect confirmation actor rejection example:
  `examples/fail/fulfillment-receipt-wrong-confirmation-actor.example.json`.

### Changed

- Extended `scripts/validate_examples.py` to validate fulfillment
  receipts and their referenced commitments.
- Added delivery-to-term matching, allocation bounds, event ordering,
  and beneficiary confirmation checks.
- Added matching delivery metadata and non-overlapping allocation
  checks across receipts.
- Added exact quantity arithmetic using scaled integers.
- Added per-commitment accepted, pending, rejected, disputed,
  and remaining quantity summaries.
- Added `unfulfilled`, `partial`, and `fulfilled` summary statuses.
- Added rejection when accepted quantity exceeds promised quantity.
- Suppressed definitive summaries for invalid datasets.

### Validation

- Expanded the registered suite from seven to nine examples.
- GitHub Actions passed all nine registered examples.
- The partial fulfillment example verifies 40 accepted hours
  against a 100-hour commitment, leaving 60 hours remaining.
- Dedicated integration examples for shared evidence, overlapping
  allocations, metadata consistency, and quantity limits were
  added in v0.5.

### Compatibility

- Added a new record type without changing the agreement,
  acceptance, or commitment schemas.
- Derived summaries are validator output, not a new protocol record.
- No receipt replacement or status-transition mechanism was introduced.

## v0.3 — Return commitments

### Added

- `schemas/return-commitment.schema.json` with schema version `0.3.0`.
- Activation requirements in `specs/return-commitment.md`.
- Commitments bound to one term of an exact agreement version
  and content digest.
- Acceptance references covering every agreement party exactly once.
- Activation timestamps, actor identification, and evidence references.
- Commitment example:
  `examples/pass/return-commitment-basic.example.json`.
- Incorrect activation actor rejection example:
  `examples/fail/return-commitment-wrong-activation-actor.example.json`.

### Changed

- Extended `scripts/validate_examples.py` to validate commitment
  identities, agreement bindings, term references, and acceptances.
- Added uniqueness checks for commitment IDs and for commitments
  referencing the same agreement ID, version, and term.
- Added activation-period, deadline, and acceptance-order checks.
- Required provider attestation for unconditional triggers and
  designated-verifier attestation for evidence-required triggers.

### Validation

- Expanded the registered suite from five to seven examples.
- GitHub Actions passed all seven registered examples.

### Compatibility

- Added a new record type without changing the agreement
  or acceptance schemas.
- Commitments inherit obligation details from agreement terms.
- The same acceptance may support multiple commitments under
  the same agreement version.
- Commitment activation does not imply fulfillment.

## v0.2 — Agreement acceptances

### Added

- `schemas/agreement-acceptance.schema.json` with schema version `0.2.0`.
- Acceptance requirements in `specs/agreement-acceptance.md`.
- Individual party acceptance bound to agreement ID, version,
  and content digest.
- Acceptance timestamps, authority references, and consent
  evidence references.
- Acceptance example:
  `examples/pass/agreement-acceptance-basic.example.json`.
- Incorrect agreement digest rejection example:
  `examples/fail/agreement-acceptance-wrong-digest.example.json`.
- Self-contained datasets using a non-empty `records` array.

### Changed

- Extended `scripts/validate_examples.py` to resolve agreements
  within the supplied dataset.
- Added acceptance identity, party membership, digest binding,
  and acceptance-time checks.
- Added uniqueness checks for acceptance IDs and individual
  party acceptances of an agreement version.
- Made cross-record validation independent of record order.

### Validation

- Expanded the registered suite from three to five examples.
- GitHub Actions passed all five registered examples.

### Compatibility

- Added a new record type without changing the agreement schema.
- An agreement record alone does not establish party consent.
- Partial party acceptance may be structurally valid but does
  not authorize commitment activation.
- Authority and consent references do not authenticate their contents.

## v0.1 — Versioned reciprocity agreements

### Added

- `schemas/reciprocity-agreement.schema.json` with schema version `0.1.0`.
- Core requirements in `specs/reciprocity-core.md`.
- Agreement identity, version, parties, validity period,
  project reference, and external references.
- Separate terms for independently measurable obligations.
- Term providers, beneficiaries, resources, quantities, units,
  activation triggers, deadlines, and confirmation procedures.
- Agreement content digests using SHA-256 over RFC 8785
  canonical JSON, excluding the top-level `agreement_digest`.
- Agreement example:
  `examples/pass/reciprocity-agreement-basic.example.json`.
- Digest mismatch rejection example:
  `examples/fail/reciprocity-agreement-digest-mismatch.example.json`.
- Duplicate term ID rejection example:
  `examples/fail/reciprocity-agreement-duplicate-term-id.example.json`.
- Reference validation in `scripts/validate_examples.py`.
- Python dependencies in `requirements.txt`.
- GitHub Actions validation in `.github/workflows/validate.yml`.

### Validation

- Registered one valid and two deliberately invalid examples.
- GitHub Actions passed all three registered examples.
- Added JSON Schema validation, duplicate JSON property rejection,
  digest verification, term identity checks, party checks,
  and agreement time checks.

### Scope

- Established versioned agreement content as the foundation
  for later acceptance, commitment, and fulfillment records.
- Kept external return mechanisms, settlement execution,
  and organizational connections outside this protocol's scope.
