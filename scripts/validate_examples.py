#!/usr/bin/env python3
"""Validate reciprocity protocol examples and self-contained datasets."""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]

SCHEMA_PATHS = {
    "reciprocity_agreement": (
        "schemas/reciprocity-agreement.schema.json"
    ),
    "agreement_acceptance": (
        "schemas/agreement-acceptance.schema.json"
    ),
    "return_commitment": (
        "schemas/return-commitment.schema.json"
    ),
    "fulfillment_receipt": (
        "schemas/fulfillment-receipt.schema.json"
    ),
}

EXPECTED_CASES = {
    "examples/pass/reciprocity-agreement-basic.example.json": set(),
    "examples/fail/reciprocity-agreement-digest-mismatch.example.json": {
        "DIGEST_MISMATCH",
    },
    "examples/fail/reciprocity-agreement-duplicate-term-id.example.json": {
        "DUPLICATE_TERM_ID",
    },
    "examples/pass/agreement-acceptance-basic.example.json": set(),
    "examples/fail/agreement-acceptance-wrong-digest.example.json": {
        "ACCEPTANCE_DIGEST_MISMATCH",
    },
    "examples/pass/return-commitment-basic.example.json": set(),
    "examples/fail/return-commitment-wrong-activation-actor.example.json": {
        "ACTIVATION_ACTOR",
    },
    "examples/pass/fulfillment-receipt-partial.example.json": set(),
    "examples/fail/fulfillment-receipt-wrong-confirmation-actor.example.json": {
        "CONFIRMATION_ACTOR",
    },
}

PARTIAL_EXAMPLE = (
    "examples/pass/fulfillment-receipt-partial.example.json"
)

QUANTITY_SCALE = 10**18

UTC_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?:\.(\d+))?Z$"
)

QUANTITY_PATTERN = re.compile(
    r"^(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,18})?$"
)


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON property: {key}")
        result[key] = value
    return result


def reject_nonfinite_number(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(
            handle,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_number,
        )


def json_pointer(parts):
    escaped = [
        str(part).replace("~", "~0").replace("/", "~1")
        for part in parts
    ]
    return "/" + "/".join(escaped) if escaped else "(root)"


def parse_utc(value):
    """Return an exactly comparable UTC timestamp, including fractions."""
    match = UTC_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"Unsupported UTC timestamp: {value}")

    seconds = datetime.strptime(
        match.group(1),
        "%Y-%m-%dT%H:%M:%S",
    )

    # Strip trailing zeros so equal fractions have equal representations.
    # Lexicographic comparison then preserves fractional time ordering.
    fraction = (match.group(2) or "").rstrip("0")
    return seconds, fraction


def quantity_to_int(value):
    """Convert a decimal quantity into exact units of 10^-18."""
    if QUANTITY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Unsupported decimal quantity: {value}")

    whole, separator, fraction = value.partition(".")
    if not separator:
        fraction = ""

    return (
        int(whole) * QUANTITY_SCALE
        + int(fraction.ljust(18, "0"))
    )


def format_quantity(value):
    sign = "-" if value < 0 else ""
    whole, fraction = divmod(abs(value), QUANTITY_SCALE)

    if fraction == 0:
        return f"{sign}{whole}"

    fractional_text = f"{fraction:018d}".rstrip("0")
    return f"{sign}{whole}.{fractional_text}"


def agreement_key(record):
    return record["agreement_id"], record["agreement_version"]


def schema_issues(document, validator):
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            json_pointer(error.absolute_path),
            error.message,
        ),
    )
    return [
        (
            "SCHEMA",
            f"{json_pointer(error.absolute_path)}: {error.message}",
        )
        for error in errors
    ]


def extract_records(document):
    if not isinstance(document, dict):
        raise ValueError("The document must be a JSON object.")

    if "records" not in document:
        return [document]

    if set(document) != {"records"}:
        raise ValueError(
            "A dataset container may contain only 'records'."
        )

    records = document["records"]
    if not isinstance(records, list) or not records:
        raise ValueError("'records' must be a non-empty array.")

    return records


def validate_agreement(record):
    issues = []
    parties = set(record["parties"])
    seen_terms = set()

    for term in record["terms"]:
        term_id = term["term_id"]

        if term_id in seen_terms:
            issues.append((
                "DUPLICATE_TERM_ID",
                f"Repeated term_id: {term_id}",
            ))
        seen_terms.add(term_id)

        for field in ("provider_id", "beneficiary_id"):
            if term[field] not in parties:
                issues.append((
                    "PARTY_NOT_FOUND",
                    f"{term_id}: {field} is not an agreement party.",
                ))

        if term["provider_id"] == term["beneficiary_id"]:
            issues.append((
                "SAME_PROVIDER_BENEFICIARY",
                f"{term_id}: provider and beneficiary must differ.",
            ))

        trigger = term["trigger"]
        if (
            trigger["type"] == "evidence_required"
            and trigger["verifier_party_id"] not in parties
        ):
            issues.append((
                "VERIFIER_NOT_FOUND",
                f"{term_id}: verifier is not an agreement party.",
            ))

    try:
        created = parse_utc(record["created_at"])
        valid_from = parse_utc(record["valid_from"])
        valid_until = parse_utc(record["valid_until"])

        if not created <= valid_from < valid_until:
            issues.append((
                "AGREEMENT_TIME",
                "Expected created_at <= valid_from < valid_until.",
            ))

        for term in record["terms"]:
            if parse_utc(term["due_at"]) < valid_from:
                issues.append((
                    "TERM_DEADLINE",
                    f"{term['term_id']}: due_at precedes valid_from.",
                ))
    except ValueError as exc:
        issues.append(("DATETIME_PARSE", str(exc)))

    payload = {
        key: value
        for key, value in record.items()
        if key != "agreement_digest"
    }

    try:
        canonical = rfc8785.dumps(payload)
        calculated = (
            "sha256:" + hashlib.sha256(canonical).hexdigest()
        )
        if record["agreement_digest"] != calculated:
            issues.append((
                "DIGEST_MISMATCH",
                f"Expected agreement_digest: {calculated}",
            ))
    except rfc8785.CanonicalizationError as exc:
        issues.append(("CANONICALIZATION", str(exc)))

    return issues


def validate_acceptance(record, agreement):
    issues = []

    if (
        record["agreement"]["agreement_digest"]
        != agreement["agreement_digest"]
    ):
        issues.append((
            "ACCEPTANCE_DIGEST_MISMATCH",
            "Acceptance digest does not match the agreement.",
        ))

    if record["party_id"] not in agreement["parties"]:
        issues.append((
            "ACCEPTANCE_PARTY_NOT_FOUND",
            "Accepting party is not an agreement party.",
        ))

    try:
        accepted = parse_utc(record["accepted_at"])
        created = parse_utc(agreement["created_at"])
        valid_until = parse_utc(agreement["valid_until"])

        if not created <= accepted < valid_until:
            issues.append((
                "ACCEPTANCE_TIME",
                "Expected created_at <= accepted_at < valid_until.",
            ))
    except ValueError as exc:
        issues.append(("DATETIME_PARSE", str(exc)))

    return issues


def validate_document(document, validators):
    """Return (issues, summaries); invalid datasets have no summaries."""
    try:
        records = extract_records(document)
    except ValueError as exc:
        return [("INPUT_ERROR", str(exc))], []

    issues = []
    invalid_indices = set()

    def add(index, code, message):
        invalid_indices.add(index)
        issues.append((code, f"record[{index}]: {message}"))

    def append_at(index, found):
        for code, message in found:
            add(index, code, message)

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            add(index, "SCHEMA", "Record must be an object.")
            continue

        record_type = record.get("record_type")
        if (
            not isinstance(record_type, str)
            or record_type not in validators
        ):
            add(index, "SCHEMA", "Unsupported record_type.")
            continue

        append_at(
            index,
            schema_issues(record, validators[record_type]),
        )

    # Semantic validation assumes every record is schema-valid.
    if issues:
        return issues, []

    agreements = defaultdict(list)
    acceptances = defaultdict(list)
    party_acceptances = defaultdict(list)
    commitments = defaultdict(list)
    term_commitments = defaultdict(list)
    receipts = defaultdict(list)

    for index, record in enumerate(records):
        record_type = record["record_type"]

        if record_type == "reciprocity_agreement":
            agreements[agreement_key(record)].append(index)

        elif record_type == "agreement_acceptance":
            acceptances[record["acceptance_id"]].append(index)
            key = (
                *agreement_key(record["agreement"]),
                record["party_id"],
            )
            party_acceptances[key].append(index)

        elif record_type == "return_commitment":
            commitments[record["commitment_id"]].append(index)
            key = (
                *agreement_key(record["agreement"]),
                record["term_id"],
            )
            term_commitments[key].append(index)

        elif record_type == "fulfillment_receipt":
            receipts[record["receipt_id"]].append(index)

    def reject_duplicates(groups, code):
        for key, indices in groups.items():
            if len(indices) > 1:
                for index in indices:
                    add(index, code, f"Duplicate identity: {key}")

    reject_duplicates(agreements, "DUPLICATE_AGREEMENT")
    reject_duplicates(acceptances, "DUPLICATE_ACCEPTANCE_ID")
    reject_duplicates(
        party_acceptances,
        "DUPLICATE_PARTY_ACCEPTANCE",
    )
    reject_duplicates(commitments, "DUPLICATE_COMMITMENT_ID")
    reject_duplicates(
        term_commitments,
        "DUPLICATE_TERM_COMMITMENT",
    )
    reject_duplicates(receipts, "DUPLICATE_RECEIPT_ID")

    for index, record in enumerate(records):
        if record["record_type"] == "reciprocity_agreement":
            append_at(index, validate_agreement(record))

    def resolve_agreement(index, reference):
        matches = agreements.get(agreement_key(reference), [])

        if not matches:
            add(index, "MISSING_AGREEMENT", "Agreement not found.")
            return None

        if len(matches) != 1:
            add(
                index,
                "AMBIGUOUS_AGREEMENT",
                "Agreement reference is not unique.",
            )
            return None

        target = matches[0]
        if target in invalid_indices:
            add(
                index,
                "INVALID_REFERENCED_AGREEMENT",
                "Referenced agreement is invalid.",
            )
            return None

        return records[target]

    for index, record in enumerate(records):
        if record["record_type"] != "agreement_acceptance":
            continue

        agreement = resolve_agreement(index, record["agreement"])
        if agreement is not None:
            append_at(
                index,
                validate_acceptance(record, agreement),
            )

    commitment_terms = {}

    for index, record in enumerate(records):
        if record["record_type"] != "return_commitment":
            continue

        reference = record["agreement"]
        agreement = resolve_agreement(index, reference)
        if agreement is None:
            continue

        if (
            reference["agreement_digest"]
            != agreement["agreement_digest"]
        ):
            add(
                index,
                "COMMITMENT_DIGEST_MISMATCH",
                "Commitment digest does not match the agreement.",
            )
            continue

        term = next(
            (
                item
                for item in agreement["terms"]
                if item["term_id"] == record["term_id"]
            ),
            None,
        )
        if term is None:
            add(index, "MISSING_TERM", "Referenced term not found.")
            continue

        commitment_terms[index] = term
        selected = []

        for acceptance_id in record["acceptance_ids"]:
            matches = acceptances.get(acceptance_id, [])

            if not matches:
                add(
                    index,
                    "MISSING_ACCEPTANCE",
                    f"Acceptance not found: {acceptance_id}",
                )
                continue

            if len(matches) != 1:
                add(
                    index,
                    "AMBIGUOUS_ACCEPTANCE",
                    f"Acceptance is not unique: {acceptance_id}",
                )
                continue

            target = matches[0]
            if target in invalid_indices:
                add(
                    index,
                    "INVALID_REFERENCED_ACCEPTANCE",
                    f"Acceptance is invalid: {acceptance_id}",
                )
                continue

            acceptance = records[target]
            if acceptance["agreement"] != reference:
                add(
                    index,
                    "COMMITMENT_ACCEPTANCE_BINDING",
                    "Acceptance refers to a different agreement "
                    "ID, version, or digest.",
                )
                continue

            selected.append(acceptance)

        accepted_parties = [
            item["party_id"] for item in selected
        ]
        if (
            len(selected) != len(record["acceptance_ids"])
            or len(accepted_parties) != len(set(accepted_parties))
            or set(accepted_parties) != set(agreement["parties"])
        ):
            add(
                index,
                "CONSENT_INCOMPLETE",
                "Acceptances must cover every agreement party "
                "exactly once.",
            )

        try:
            activated = parse_utc(record["activated_at"])
            valid_from = parse_utc(agreement["valid_from"])
            valid_until = parse_utc(agreement["valid_until"])
            due = parse_utc(term["due_at"])

            if not valid_from <= activated < valid_until:
                add(
                    index,
                    "ACTIVATION_TIME",
                    "Activation must fall within the agreement's "
                    "activation period.",
                )

            if activated > due:
                add(
                    index,
                    "ACTIVATION_AFTER_DEADLINE",
                    "Activation occurs after the term deadline.",
                )

            if any(
                parse_utc(item["accepted_at"]) > activated
                for item in selected
            ):
                add(
                    index,
                    "ACCEPTANCE_AFTER_ACTIVATION",
                    "Acceptance occurs after activation.",
                )
        except ValueError as exc:
            add(index, "DATETIME_PARSE", str(exc))

        trigger = term["trigger"]
        expected_actor = (
            term["provider_id"]
            if trigger["type"] == "unconditional"
            else trigger["verifier_party_id"]
        )
        if record["activation"]["attested_by"] != expected_actor:
            add(
                index,
                "ACTIVATION_ACTOR",
                f"Expected activation actor: {expected_actor}",
            )

    delivery_groups = defaultdict(list)
    receipt_targets = {}

    for index, record in enumerate(records):
        if record["record_type"] != "fulfillment_receipt":
            continue

        delivery = record["delivery"]
        delivery_groups[delivery["delivery_id"]].append(index)

        matches = commitments.get(record["commitment_id"], [])

        if not matches:
            add(
                index,
                "MISSING_COMMITMENT",
                "Referenced commitment not found.",
            )
            continue

        if len(matches) != 1:
            add(
                index,
                "AMBIGUOUS_COMMITMENT",
                "Referenced commitment is not unique.",
            )
            continue

        target = matches[0]
        if target in invalid_indices:
            add(
                index,
                "INVALID_REFERENCED_COMMITMENT",
                "Referenced commitment is invalid.",
            )
            continue

        commitment = records[target]
        term = commitment_terms[target]
        receipt_targets[index] = target

        for field in (
            "provider_id",
            "beneficiary_id",
            "resource_id",
            "unit",
        ):
            if delivery[field] != term[field]:
                add(
                    index,
                    "DELIVERY_TERM_MISMATCH",
                    f"delivery.{field} does not match the term.",
                )

        start = quantity_to_int(record["slice_start"])
        quantity = quantity_to_int(record["quantity"])
        total = quantity_to_int(delivery["total_quantity"])

        if (
            start < 0
            or quantity <= 0
            or total <= 0
            or start + quantity > total
        ):
            add(
                index,
                "DELIVERY_SLICE_BOUNDS",
                "The allocated slice must be positive and fit "
                "within the delivery total.",
            )

        try:
            activated = parse_utc(commitment["activated_at"])
            delivered = parse_utc(delivery["delivered_at"])
            issued = parse_utc(record["issued_at"])

            if not activated <= delivered <= issued:
                add(
                    index,
                    "RECEIPT_TIME",
                    "Expected activated_at <= delivered_at "
                    "<= issued_at.",
                )

            confirmation = record.get("confirmation")
            if confirmation is not None:
                confirmed = parse_utc(confirmation["confirmed_at"])
                if confirmed < issued:
                    add(
                        index,
                        "CONFIRMATION_TIME",
                        "confirmed_at must not precede issued_at.",
                    )
        except ValueError as exc:
            add(index, "DATETIME_PARSE", str(exc))

        confirmation = record.get("confirmation")
        if (
            confirmation is not None
            and confirmation["by_party_id"] != term["beneficiary_id"]
        ):
            add(
                index,
                "CONFIRMATION_ACTOR",
                "Confirmation actor must be the term beneficiary.",
            )

    # Evidence references may be reused. Delivery allocations may not.
    # All statuses reserve their slices, including rejected/disputed.
    for delivery_id, indices in delivery_groups.items():
        baseline = records[indices[0]]["delivery"]

        if any(
            records[index]["delivery"] != baseline
            for index in indices[1:]
        ):
            for index in indices:
                add(
                    index,
                    "DELIVERY_METADATA_MISMATCH",
                    f"Inconsistent metadata for {delivery_id}.",
                )

        intervals = []
        for index in indices:
            record = records[index]
            start = quantity_to_int(record["slice_start"])
            end = start + quantity_to_int(record["quantity"])
            intervals.append((start, end, index))

        intervals.sort()
        furthest_end = None
        furthest_index = None
        overlapping_indices = set()

        for start, end, index in intervals:
            if furthest_end is not None and start < furthest_end:
                overlapping_indices.add(index)
                overlapping_indices.add(furthest_index)

            if furthest_end is None or end > furthest_end:
                furthest_end = end
                furthest_index = index

        for index in sorted(overlapping_indices):
            add(
                index,
                "DELIVERY_SLICE_OVERLAP",
                f"Overlapping allocation for {delivery_id}.",
            )

    # Do not publish definitive totals for an invalid record set.
    if issues:
        return issues, []

    totals = {}
    for index, term in commitment_terms.items():
        totals[index] = {
            "pending": 0,
            "accepted": 0,
            "rejected": 0,
            "disputed": 0,
        }

    for receipt_index, target in receipt_targets.items():
        record = records[receipt_index]
        totals[target][record["confirmation_status"]] += (
            quantity_to_int(record["quantity"])
        )

    summaries = []

    for index, term in commitment_terms.items():
        record = records[index]
        quantities = totals[index]
        promised = quantity_to_int(term["quantity"])
        accepted = quantities["accepted"]

        if accepted > promised:
            add(
                index,
                "ACCEPTED_QUANTITY_EXCEEDED",
                "Accepted quantity exceeds the commitment quantity.",
            )
            continue

        if accepted == 0:
            status = "unfulfilled"
        elif accepted < promised:
            status = "partial"
        else:
            status = "fulfilled"

        summaries.append({
            "commitment_id": record["commitment_id"],
            "unit": term["unit"],
            "promised_quantity": format_quantity(promised),
            "accepted_quantity": format_quantity(accepted),
            "remaining_quantity": format_quantity(
                promised - accepted
            ),
            "pending_quantity": format_quantity(
                quantities["pending"]
            ),
            "rejected_quantity": format_quantity(
                quantities["rejected"]
            ),
            "disputed_quantity": format_quantity(
                quantities["disputed"]
            ),
            "status": status,
        })

    if issues:
        return issues, []

    summaries.sort(key=lambda item: item["commitment_id"])
    return [], summaries


def validate_file(path, validators):
    try:
        document = read_json(path)
    except (OSError, ValueError, UnicodeError) as exc:
        return [("INPUT_ERROR", str(exc))], []

    return validate_document(document, validators)


def print_issues(issues):
    for code, message in issues:
        print(f"  {code}: {message}")


def print_summaries(summaries):
    for summary in summaries:
        print(
            "  SUMMARY "
            + json.dumps(summary, ensure_ascii=False, sort_keys=True)
        )


def partial_summary_matches(summaries):
    if len(summaries) != 1:
        return False

    expected = {
        "commitment_id": (
            "urn:example:commitment:compute-100-hours-001"
        ),
        "unit": {
            "namespace": "urn:example:unit:compute-service-a-v1",
            "code": "HOUR",
        },
        "promised_quantity": "100",
        "accepted_quantity": "40",
        "remaining_quantity": "60",
        "pending_quantity": "0",
        "rejected_quantity": "0",
        "disputed_quantity": "0",
        "status": "partial",
    }
    return summaries[0] == expected


def run_examples(validators):
    passed = 0

    for relative_path, expected_codes in EXPECTED_CASES.items():
        issues, summaries = validate_file(
            ROOT / relative_path,
            validators,
        )
        actual_codes = {code for code, _ in issues}
        success = actual_codes == expected_codes

        if relative_path == PARTIAL_EXAMPLE:
            success = success and partial_summary_matches(summaries)

        label = "PASS" if success else "FAIL"
        print(
            f"[{label}] {relative_path} "
            f"codes={sorted(actual_codes)}"
        )

        if success:
            passed += 1
        else:
            print(f"  Expected codes: {sorted(expected_codes)}")
            print_issues(issues)

            if relative_path == PARTIAL_EXAMPLE:
                print(
                    "  Expected summary: promised=100, accepted=40, "
                    "remaining=60, status=partial."
                )
                print_summaries(summaries)

    total = len(EXPECTED_CASES)
    print(f"\n{passed}/{total} examples passed.")
    return 0 if passed == total else 1


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Validate bundled examples or a self-contained "
            "reciprocity protocol dataset."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help=(
            "Validate one JSON file. Relative paths are resolved "
            "from the repository root."
        ),
    )
    args = parser.parse_args()

    checker = FormatChecker()
    for required_format in ("uri", "date-time"):
        if required_format not in checker.checkers:
            print(
                f"SETUP_ERROR: Missing format checker: "
                f"{required_format}",
                file=sys.stderr,
            )
            return 2

    validators = {}

    try:
        for record_type, relative_path in SCHEMA_PATHS.items():
            schema = read_json(ROOT / relative_path)
            Draft202012Validator.check_schema(schema)
            validators[record_type] = Draft202012Validator(
                schema,
                format_checker=checker,
            )
    except (OSError, ValueError, UnicodeError, SchemaError) as exc:
        print(f"SETUP_ERROR: {exc}", file=sys.stderr)
        return 2

    if args.dataset is None:
        return run_examples(validators)

    dataset_path = args.dataset
    if not dataset_path.is_absolute():
        dataset_path = ROOT / dataset_path

    issues, summaries = validate_file(dataset_path, validators)

    if issues:
        codes = sorted({code for code, _ in issues})
        print(f"INVALID codes={codes}")
        print_issues(issues)
        return 1

    print("VALID")
    print_summaries(summaries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
