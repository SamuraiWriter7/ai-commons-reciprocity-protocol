# ai-commons-reciprocity-protocol

A protocol for versioned reciprocity agreements, party acceptances,
return commitments, and fulfillment verification across organizations
collaborating on AI.

## Overview

This protocol connects agreed obligations with reported deliveries
and beneficiary confirmations.

It answers four questions:

1. Which version of the agreement defines the terms?
2. Which parties accepted that exact version and content?
3. Which individual commitments were activated?
4. Which deliveries were allocated to those commitments and accepted?

Its core principle is:

> Evidence may be shared. The same quantity of the same delivery
> must not be counted twice.

The repository provides four JSON Schemas, record specifications,
example datasets, and a Python reference validator.

## Status

Project version: **v0.5**

The registered example suite contains **14 datasets**:
five valid examples and nine deliberately invalid examples.
The v0.5 suite has passed GitHub Actions.

Passing the suite confirms the registered cases. It does not
constitute exhaustive testing or verification of real-world delivery.

v0.5 consolidates integration validation and conformance documentation.
It introduces no additional record type.

## Scope

The protocol focuses on:

- Immutable agreement versions and content digests.
- Individual party acceptances and authority evidence references.
- Separate commitments for separately measurable obligations.
- Delivery declarations, beneficiary confirmations, and disputes.
- Exact quantity accounting and duplicate-allocation detection.

Existing return, settlement, and organizational connection
specifications remain responsible for their own functions.

This protocol can reference their records as evidence or delivery
sources. It does not define payment execution, monetary valuation,
organization federation, or dispute resolution.

## Four record types

| Record type | Purpose | Schema |
| --- | --- | --- |
| `reciprocity_agreement` | Agreement parties, terms, quantities, triggers, deadlines, and confirmation procedures | `schemas/reciprocity-agreement.schema.json` |
| `agreement_acceptance` | A party's acceptance of an exact agreement version and digest, with authority and consent evidence references | `schemas/agreement-acceptance.schema.json` |
| `return_commitment` | Activation of one agreement term, supported by the required party acceptances | `schemas/return-commitment.schema.json` |
| `fulfillment_receipt` | Allocation of a delivery quantity to a commitment, with pending, accepted, rejected, or disputed status | `schemas/fulfillment-receipt.schema.json` |

An agreement contains one or more terms.
Each acceptance binds a party to an exact agreement version and digest.
Each commitment activates one term.
Each receipt allocates part or all of a delivery to one commitment.

The commitment inherits its obligation from the referenced term.
It does not restate the promised quantity, resource, or unit.

## Core rules

### Bind consent to exact content

An acceptance references:

- `agreement_id`
- `agreement_version`
- `agreement_digest`

The digest is SHA-256 over the RFC 8785 canonical representation
of the agreement, excluding only its top-level `agreement_digest`.

Changing agreement content requires a new version and new acceptances.
An acceptance of an earlier version does not authorize the changed terms.

### Keep different obligations separate

An obligation to provide 100 compute hours and an obligation to
provide 20 training seats use different term and commitment IDs.

Their fulfillment quantities are evaluated separately, using the
resource and unit defined by each term.

The validator does not convert between units or combine different
resources into a common value.

### Activate with complete consent

A commitment must reference valid acceptances covering every
agreement party exactly once.

Activation must occur within the agreement's activation period,
at or before the term deadline, and after all referenced acceptances.

For an unconditional trigger, the provider attests activation.
For an evidence-required trigger, the designated verifier attests it.

Partial acceptance records may form a valid dataset, but they do
not authorize commitment activation.

### Separate evidence from delivery identity

`evidence_refs` identify supporting material.
`delivery.delivery_id` identifies the delivery being allocated.

A report may support several receipts.
Sharing that report does not itself constitute double counting.

Records with the same `delivery_id` must contain matching
`delivery` metadata. The same actual delivery must retain a stable ID.

### Allocate non-overlapping quantities

Each receipt allocates this half-open quantity interval:

```text
[slice_start, slice_start + quantity)
```

For a delivery of 100 hours:

| First allocation | Second allocation | Result |
| --- | --- | --- |
| `[0, 40)` | `[40, 100)` | Valid: adjacent quantities |
| `[0, 40)` | `[30, 90)` | Invalid: 10 hours overlap |
| `[0, 40)` to commitment A | `[0, 40)` to commitment B | Invalid: the same 40 hours are counted twice |

These intervals are quantity coordinates, not timestamps.

Overlap checks apply across all commitments in the supplied dataset.
All confirmation statuses reserve their slices.

### Count accepted quantities only

The receipt statuses are:

| Status | Confirmation | Counts toward fulfillment |
| --- | --- | --- |
| `pending` | Absent | No |
| `accepted` | Required | Yes |
| `rejected` | Required, with a reason | No |
| `disputed` | Required, with a reason | No |

When confirmation is present, its actor must be the commitment
term's beneficiary.

For a valid dataset:

```text
accepted_quantity = sum of accepted receipt quantities
remaining_quantity = promised_quantity - accepted_quantity
```

Accepted quantity must not exceed promised quantity.

| Accepted quantity | Fulfillment status |
| --- | --- |
| Zero | `unfulfilled` |
| Greater than zero but below the promise | `partial` |
| Equal to the promise | `fulfilled` |

Calculations use exact decimal quantities.
The reference validator performs arithmetic with scaled integers
to avoid rounding errors.

An invalid dataset produces no definitive fulfillment summaries.

## Example: shared evidence without double counting

The dataset at
`examples/pass/fulfillment-receipt-shared-evidence.example.json`
contains:

- An agreement promising 100 compute hours.
- Acceptances from both parties.
- An activated commitment for those hours.
- One delivery totaling 100 hours.
- Two accepted receipts allocating 40 and 60 hours.
- A shared report referenced by both receipts.

The allocations are `[0, 40)` and `[40, 100)`.

The expected commitment summary is:

```json
{
  "commitment_id": "urn:example:commitment:compute-100-hours-001",
  "unit": {
    "namespace": "urn:example:unit:compute-service-a-v1",
    "code": "HOUR"
  },
  "promised_quantity": "100",
  "accepted_quantity": "100",
  "remaining_quantity": "0",
  "pending_quantity": "0",
  "rejected_quantity": "0",
  "disputed_quantity": "0",
  "status": "fulfilled"
}
```

This summary is derived validator output, not a fifth protocol record.

## Quick start

The GitHub Actions workflow uses Python 3.12.

Run the following commands from the repository root.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the registered example suite:

```bash
python scripts/validate_examples.py
```

Expected final output:

```text
14/14 examples passed.
```

A deliberately invalid example counts as a passing test when the
validator rejects it with exactly the expected error-code set.

Validate one dataset:

```bash
python scripts/validate_examples.py --dataset examples/pass/fulfillment-receipt-shared-evidence.example.json
```

A valid dataset prints `VALID` and any commitment summaries.
An invalid dataset prints `INVALID` and diagnostics.

| Exit code | Meaning |
| --- | --- |
| `0` | Suite expectations matched, or the selected dataset is valid |
| `1` | A suite expectation failed, or the selected dataset is invalid |
| `2` | Setup or command-line argument error |

In dataset mode, a deliberately invalid example returns `1`.

## Dataset format

The validator accepts a single record or an object containing only
a non-empty `records` array.

All referenced protocol records must be included in the same dataset.
Record order does not affect validity or fulfillment totals.

External evidence and procedure references are not fetched.

Each example file is independent. Identifiers reused across example
files do not cause conflicts because the files are validated separately.

The suite runs the paths explicitly registered in
`scripts/validate_examples.py`. Adding another example file does
not automatically register it.

## Specifications and supporting files

All paths below are relative to the repository root.

| Path | Contents |
| --- | --- |
| `specs/reciprocity-core.md` | Agreement identity, terms, digest, and core invariants |
| `specs/agreement-acceptance.md` | Individual consent and agreement binding |
| `specs/return-commitment.md` | Commitment activation and consent requirements |
| `specs/fulfillment-receipt.md` | Delivery allocation, confirmation, and quantity accounting |
| `specs/conformance.md` | Integrated validation requirements, 14 example expectations, and verification boundaries |
| `scripts/validate_examples.py` | Reference validator and registered example runner |
| `requirements.txt` | Python validation dependencies |
| `.github/workflows/validate.yml` | GitHub Actions validation workflow |

## Versioning

Project versions and record schema versions are managed separately.

| Project stage | Main addition |
| --- | --- |
| v0.1 | Versioned reciprocity agreements |
| v0.2 | Individual party acceptances |
| v0.3 | Activated return commitments |
| v0.4 | Fulfillment receipts and quantity summaries |
| v0.5 | Integration examples and consolidated conformance requirements |

The schema versions used by v0.5 remain:

| Schema | `schema_version` |
| --- | --- |
| `schemas/reciprocity-agreement.schema.json` | `0.1.0` |
| `schemas/agreement-acceptance.schema.json` | `0.2.0` |
| `schemas/return-commitment.schema.json` | `0.3.0` |
| `schemas/fulfillment-receipt.schema.json` | `0.4.0` |

`agreement_version` identifies the agreed content.
It is distinct from both the project version and `schema_version`.

## Verification boundaries

Validation establishes consistency of the supplied records under
the implemented rules.

It does not authenticate parties, authority evidence, consent,
reports, or actual deliveries. It does not execute externally
referenced confirmation procedures.

A `fulfilled` summary means the accepted quantity equals the promised
quantity in that dataset. Deadline compliance is separate:
late delivery is not rejected solely because it is late.

The validator checks event ordering but does not compare events
with the current clock.

Duplicate-allocation detection is limited to the supplied dataset
and declared delivery IDs. Detecting reuse across submissions requires
shared allocation history or an equivalent coordination mechanism.
Different IDs assigned to the same actual delivery cannot be
identified as equivalent by this validator alone.

v0.5 does not define receipt replacement, revocation, or status
transitions. A rejected or disputed receipt does not automatically
release its allocation. Adding another receipt over that slice
remains an overlap.

Detailed requirements and limitations are defined in
`specs/conformance.md`.
