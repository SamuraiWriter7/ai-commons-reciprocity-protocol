# Conformance — v0.5

## 1. Purpose

This document defines the validation requirements for
ai-commons-reciprocity-protocol v0.5.

The protocol connects four kinds of records:

- Versioned reciprocity agreements.
- Individual party acceptances.
- Activated return commitments.
- Fulfillment declarations and beneficiary confirmations.

Its central rule is:

> Evidence may be shared. The same quantity of the same delivery
> MUST NOT be allocated more than once.

This document uses MUST and MUST NOT for mandatory requirements,
SHOULD for recommendations, and MAY for permitted behavior.

## 2. Versioning and schemas

The project version and individual schema versions are separate.

v0.5 adds integration validation and conformance examples.
It does not introduce a new record type or change the existing
schema versions.

| Record type | Schema path | schema_version |
| --- | --- | --- |
| reciprocity_agreement | `schemas/reciprocity-agreement.schema.json` | `0.1.0` |
| agreement_acceptance | `schemas/agreement-acceptance.schema.json` | `0.2.0` |
| return_commitment | `schemas/return-commitment.schema.json` | `0.3.0` |
| fulfillment_receipt | `schemas/fulfillment-receipt.schema.json` | `0.4.0` |

The schemas use JSON Schema Draft 2020-12.

The corresponding record specifications are:

- `specs/reciprocity-core.md`
- `specs/agreement-acceptance.md`
- `specs/return-commitment.md`
- `specs/fulfillment-receipt.md`

A record MUST satisfy both its schema and the applicable semantic
requirements. Schema validation alone is insufficient.

## 3. Validation input and scope

### 3.1 Input forms

The validator accepts either:

- One record as the root JSON object.
- A root object containing only a non-empty `records` array.

A dataset container has this structure:

```json
{
  "records": [
    {}
  ]
}
```

The empty object above illustrates the container only.
It is not a valid protocol record.

Duplicate JSON property names and non-finite JSON numbers
MUST be rejected.

Each record MUST declare a supported `record_type` and the
corresponding `schema_version`.

### 3.2 Self-contained references

All referenced protocol records MUST be present in the same dataset.

For example, validating a fulfillment receipt requires its
commitment, the referenced agreement, and the acceptances required
by that commitment.

External evidence and procedure references do not need to resolve
to protocol records inside the dataset.

Record order MUST NOT determine validity or fulfillment totals.
A record MAY appear before the records it references.

### 3.3 Dataset boundary

Each example file is an independent dataset.

Identifiers MAY be reused in different example files.
Records from different examples MUST NOT be implicitly combined.

Duplicate-allocation checks apply to the records supplied in one
validation operation. Separate successful validations do not prove
that the datasets are mutually consistent.

An operational deployment needs a shared allocation history or an
equivalent coordination mechanism to detect double counting across
separate submissions.

## 4. Validation layers

Validation has three layers:

1. JSON input and record schema validation.
2. Record identities, references, and semantic consistency.
3. Delivery allocation and fulfillment aggregation.

The reference validator stops before semantic validation if any
record fails schema validation.

A referenced record MUST be valid before a dependent record can
be accepted as valid.

An invalid dataset MUST NOT produce definitive fulfillment summaries,
including summaries for otherwise valid commitments in that dataset.

## 5. Agreement validation

A reciprocity agreement MUST satisfy the following requirements:

- `(agreement_id, agreement_version)` is unique within the dataset.
- Each `term_id` is unique within that agreement.
- Each term's provider and beneficiary are agreement parties.
- The provider and beneficiary are different parties.
- An evidence-required trigger's verifier is an agreement party.
- `created_at <= valid_from < valid_until`.
- Each term's `due_at` is at or after `valid_from`.

The agreement digest MUST be calculated by:

1. Removing only the top-level `agreement_digest` property.
2. Canonicalizing the remaining agreement with RFC 8785 JCS.
3. Calculating SHA-256 over the canonical bytes.
4. Encoding the result as `sha256:` followed by lowercase hexadecimal.

Array order is preserved. URI strings are not normalized.

An agreement version is immutable. Changed agreement content
requires a new version and new acceptances bound to that version
and its digest.

The validator can detect conflicts present in the supplied dataset.
Detecting replacement of a previously published version also
requires retained historical records.

## 6. Acceptance validation

An agreement acceptance MUST:

- Have a unique `acceptance_id` within the dataset.
- Reference a unique, valid agreement by ID and version.
- Match that agreement's content digest.
- Identify a party listed in the agreement.
- Satisfy `agreement.created_at <= accepted_at < agreement.valid_until`.
- Include the required authority and consent evidence references.

Only one acceptance per
`(agreement_id, agreement_version, party_id)` is permitted in a dataset.

A different digest does not permit a second acceptance for the same
party and agreement version.

A dataset containing only some parties' acceptances MAY be valid.
Partial acceptance does not authorize commitment activation.

The presence of an authority or consent evidence URI does not
establish the authenticity of its contents.

## 7. Commitment validation

A return commitment MUST:

- Have a unique `commitment_id`.
- Reference a unique, valid agreement and match its digest.
- Reference a term in that agreement.
- Be the only commitment for that agreement ID, version, and term.
- Reference valid acceptances covering every agreement party
  exactly once.
- Use acceptances bound to the same agreement ID, version, and digest.

The same acceptance MAY support multiple commitments under the
same agreement version.

All referenced acceptances MUST satisfy:

```text
accepted_at <= activated_at
```

Activation MUST satisfy:

```text
valid_from <= activated_at < valid_until
activated_at <= due_at
```

For an unconditional trigger, `activation.attested_by` MUST be
the term's provider.

For an evidence-required trigger, `activation.attested_by` MUST be
the term's designated verifier.

Activation evidence references are required in both cases.

The commitment inherits the term's provider, beneficiary, resource,
quantity, unit, deadline, and confirmation procedure.

The agreement's activation period does not end an already activated
obligation. Not every term needs to be activated in the same dataset.

## 8. Fulfillment receipt validation

### 8.1 Reference and delivery matching

A fulfillment receipt MUST:

- Have a unique `receipt_id`.
- Reference a unique, valid commitment.
- Match the commitment term's provider, beneficiary, resource,
  and unit in its `delivery` object.

Identifiers and unit strings are compared exactly.
No automatic unit conversion is performed.

`delivery.total_quantity` describes the actual delivery's total.
It is distinct from the quantity promised by a commitment.

### 8.2 Allocation slices

Each receipt allocates the half-open quantity interval:

```text
[slice_start, slice_start + quantity)
```

These are quantity coordinates within a delivery, not timestamps.

The following conditions MUST hold:

```text
slice_start >= 0
quantity > 0
delivery.total_quantity > 0
slice_start + quantity <= delivery.total_quantity
```

Adjacent slices are permitted:

```text
[0, 40) and [40, 100)
```

Overlapping slices are prohibited:

```text
[0, 40) and [30, 90)
```

A delivery MAY be only partially allocated.

### 8.3 Stable delivery identity

Records using the same `delivery_id` MUST contain the same
`delivery` object.

Object property order is irrelevant. Field values must match.
Numerically equivalent strings such as `"100"` and `"100.0"`
are not identical metadata values.

The same actual delivery MUST retain a stable `delivery_id`.
Assigning a new identifier to the same delivery does not make
double counting permissible.

`source_ref` SHOULD identify the specific external delivery event
or source record entry.

The reference validator compares declared delivery identities.
It cannot establish that different identifiers secretly refer to
the same real-world delivery.

### 8.4 Shared evidence and double counting

Multiple receipts MAY reference the same report or other evidence.

Repeated evidence references across receipts MUST NOT, by themselves,
cause rejection.

For each `delivery_id`, allocated slices MUST NOT overlap across:

- Receipts for the same commitment.
- Receipts for different commitments.
- Receipts with different confirmation statuses.

All four statuses reserve their allocated slices:

- `pending`
- `accepted`
- `rejected`
- `disputed`

A rejected or disputed receipt does not automatically release its
allocation for reuse.

### 8.5 Time ordering

A receipt MUST satisfy:

```text
commitment.activated_at <= delivery.delivered_at <= issued_at
```

When confirmation is present, it MUST also satisfy:

```text
issued_at <= confirmation.confirmed_at
```

Delivery after the term's `due_at` is not rejected solely because
it is late. Quantity fulfillment and deadline compliance are
separate questions.

The reference summary does not report deadline compliance.

Validation does not compare timestamps with the current clock.
A successful result therefore does not establish that the recorded
events have already occurred.

### 8.6 Confirmation

For `pending`, the receipt MUST NOT contain `confirmation`.

For `accepted`, `rejected`, or `disputed`, the receipt MUST contain
`confirmation`.

Whenever confirmation is present:

```text
confirmation.by_party_id == term.beneficiary_id
```

The confirmation MUST contain its timestamp, authority reference,
and evidence references.

A rejected or disputed confirmation MUST also include a reason.

The validator checks these fields and the actor relationship.
It does not authenticate the confirming party or execute the
externally referenced confirmation procedure.

### 8.7 Receipt lifecycle

v0.5 does not define receipt replacement, revocation, supersession,
or status-transition processing.

A new receipt does not automatically replace an earlier receipt.
Adding a new receipt over an existing slice remains an overlap,
even when the intention is to change its confirmation status.

## 9. Quantity arithmetic and summaries

Quantities MUST be calculated exactly, without binary floating-point
rounding or intermediate decimal rounding.

The schemas permit up to 30 integer digits and 18 fractional digits.
The reference validator converts quantities into integer units
of `10^-18` for arithmetic.

For each commitment:

```text
accepted_quantity = sum(quantity of accepted receipts)
remaining_quantity = promised_quantity - accepted_quantity
```

The following requirement MUST hold:

```text
accepted_quantity <= promised_quantity
```

Pending, rejected, and disputed quantities are totaled separately.
They do not reduce `remaining_quantity`.

The fulfillment status is:

| Condition | Status |
| --- | --- |
| accepted_quantity = 0 | `unfulfilled` |
| 0 < accepted_quantity < promised_quantity | `partial` |
| accepted_quantity = promised_quantity | `fulfilled` |

A valid commitment without receipts has zero accepted quantity
and status `unfulfilled`.

The reference summary contains:

- `commitment_id`
- `unit`
- `promised_quantity`
- `accepted_quantity`
- `remaining_quantity`
- `pending_quantity`
- `rejected_quantity`
- `disputed_quantity`
- `status`

Summaries are derived validator output, not an additional protocol
record type.

`fulfilled` means that the accepted quantity in the supplied dataset
equals the promised quantity. It does not independently establish
timely performance, evidence authenticity, or legal discharge.

## 10. Registered examples

The v0.5 example suite contains 14 independent datasets:
five valid examples and nine invalid examples.

An invalid example passes the test suite when its observed error-code
set exactly matches the expected set.

Repeated occurrences of one error code count as one member of that
set. Diagnostic message wording and record indices are not compared.

| Repository-relative path | Expected result |
| --- | --- |
| `examples/pass/reciprocity-agreement-basic.example.json` | Valid |
| `examples/fail/reciprocity-agreement-digest-mismatch.example.json` | `DIGEST_MISMATCH` |
| `examples/fail/reciprocity-agreement-duplicate-term-id.example.json` | `DUPLICATE_TERM_ID` |
| `examples/pass/agreement-acceptance-basic.example.json` | Valid |
| `examples/fail/agreement-acceptance-wrong-digest.example.json` | `ACCEPTANCE_DIGEST_MISMATCH` |
| `examples/pass/return-commitment-basic.example.json` | Valid |
| `examples/fail/return-commitment-wrong-activation-actor.example.json` | `ACTIVATION_ACTOR` |
| `examples/pass/fulfillment-receipt-partial.example.json` | Valid; partial summary |
| `examples/fail/fulfillment-receipt-wrong-confirmation-actor.example.json` | `CONFIRMATION_ACTOR` |
| `examples/pass/fulfillment-receipt-shared-evidence.example.json` | Valid; fulfilled summary |
| `examples/fail/fulfillment-receipt-overlapping-slices.example.json` | `DELIVERY_SLICE_OVERLAP` |
| `examples/fail/fulfillment-receipt-inconsistent-delivery.example.json` | `DELIVERY_METADATA_MISMATCH` |
| `examples/fail/fulfillment-receipt-accepted-quantity-exceeded.example.json` | `ACCEPTED_QUANTITY_EXCEEDED` |
| `examples/fail/fulfillment-receipt-cross-commitment-overlap.example.json` | `DELIVERY_SLICE_OVERLAP` |

The suite additionally compares complete expected summaries for:

| Repository-relative path | Promised | Accepted | Remaining | Status |
| --- | --- | --- | --- | --- |
| `examples/pass/fulfillment-receipt-partial.example.json` | 100 | 40 | 60 | `partial` |
| `examples/pass/fulfillment-receipt-shared-evidence.example.json` | 100 | 100 | 0 | `fulfilled` |

Both use `HOUR` in the
`urn:example:unit:compute-service-a-v1` namespace.
Their pending, rejected, and disputed quantities are all zero.

Every invalid example MUST produce no fulfillment summaries.

These examples provide regression coverage for the listed cases.
Passing all 14 examples is not proof that every possible invalid
input or every normative requirement has been exhaustively tested.

## 11. Running validation

Run commands from the repository root.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run all registered examples:

```bash
python scripts/validate_examples.py
```

The expected successful final line is:

```text
14/14 examples passed.
```

Validate one dataset:

```bash
python scripts/validate_examples.py --dataset examples/pass/fulfillment-receipt-shared-evidence.example.json
```

Relative dataset paths are resolved from the repository root.

In dataset mode:

- A valid dataset prints `VALID` and available commitment summaries.
- An invalid dataset prints `INVALID`, error codes, and diagnostics.
- An invalid dataset does not print fulfillment summaries.

The validator's normal exit codes are:

| Exit code | Meaning |
| --- | --- |
| 0 | All registered examples match expectations, or the selected dataset is valid |
| 1 | An example does not match expectations, or the selected dataset is invalid |
| 2 | Schema or format-checker setup failed, or command-line arguments are invalid |

A deliberately invalid example returns exit code 1 in dataset mode.
It counts as a passing test in suite mode when rejected with the
expected error-code set.

The suite runs only the examples explicitly registered in
`scripts/validate_examples.py`. Adding a JSON file alone does not
add it to the suite.

GitHub Actions runs the suite through
`.github/workflows/validate.yml`.

## 12. Verification boundaries

A successful validation establishes internal consistency under
the implemented rules for the supplied records.

It does not establish:

- The authenticity of parties, signatures, or authority evidence.
- That consent was actually given.
- That activation conditions actually occurred.
- That a reported delivery actually occurred.
- The truth or completeness of an external report.
- Completion of an externally referenced confirmation procedure.
- The completeness of the supplied allocation history.
- Absence of double counting outside the dataset.
- Equivalence between different delivery identifiers.
- Resolution of a dispute or entitlement to payment.

The reference validator does not fetch external evidence.

External return, settlement, identity, and organizational connection
specifications remain responsible for their own functions.

Deployments MUST distinguish record consistency from independently
verified real-world performance when presenting validation results.
