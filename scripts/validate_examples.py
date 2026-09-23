#!/usr/bin/env python3
"""Validate ACRP agreements, acceptances, and return commitments."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
}

# Each file is an independent validation case.
EXPECTED_CASES = {
    "examples/pass/reciprocity-agreement-basic.example.json": set(),
    "examples/fail/reciprocity-agreement-digest-mismatch.example.json": {
        "DIGEST_MISMATCH"
    },
    "examples/fail/reciprocity-agreement-duplicate-term-id.example.json": {
        "DUPLICATE_TERM_ID"
    },
    "examples/pass/agreement-acceptance-basic.example.json": set(),
    "examples/fail/agreement-acceptance-wrong-digest.example.json": {
        "ACCEPTANCE_DIGEST_MISMATCH"
    },
    "examples/pass/return-commitment-basic.example.json": set(),
    "examples/fail/return-commitment-wrong-activation-actor.example.json": {
        "ACTIVATION_ACTOR"
    },
}


def reject_duplicate_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON property: {key!r}")
        result[key] = value

    return result


def reject_nonfinite_number(value):
    raise ValueError(f"Invalid JSON numeric constant: {value}")


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(
            handle,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_number,
        )


def json_pointer(parts) -> str:
    tokens = [
        str(part).replace("~", "~0").replace("/", "~1")
        for part in parts
    ]
    return "/" + "/".join(tokens) if tokens else "(root)"


def parse_utc(value: str) -> datetime:
    # Schema validation has already required a UTC timestamp ending in Z.
    return datetime.fromisoformat(value[:-1] + "+00:00")


def agreement_key(record):
    return (
        record["agreement_id"],
        record["agreement_version"],
    )


def schema_issues(record, validator):
    errors = sorted(
        validator.iter_errors(record),
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


def validate_agreement(document):
    """Check relationships after successful schema validation."""
    issues = []

    def add(code, message):
        issues.append((code, message))

    parties = set(document["parties"])
    seen_term_ids = set()

    for index, term in enumerate(document["terms"]):
        location = f"/terms/{index}"

        if term["term_id"] in seen_term_ids:
            add(
                "DUPLICATE_TERM_ID",
                f"{location}/term_id duplicates another term.",
            )
        seen_term_ids.add(term["term_id"])

        for field in ("provider_id", "beneficiary_id"):
            if term[field] not in parties:
                add(
                    "PARTY_NOT_FOUND",
                    f"{location}/{field} is not in parties.",
                )

        if term["provider_id"] == term["beneficiary_id"]:
            add(
                "SAME_PROVIDER_BENEFICIARY",
                f"{location}: provider and beneficiary must differ.",
            )

        trigger = term["trigger"]

        if trigger["type"] == "evidence_required":
            if trigger["verifier_party_id"] not in parties:
                add(
                    "VERIFIER_NOT_FOUND",
                    f"{location}/trigger/verifier_party_id "
                    "is not in parties.",
                )

    try:
        created_at = parse_utc(document["created_at"])
        valid_from = parse_utc(document["valid_from"])
        valid_until = parse_utc(document["valid_until"])
        due_dates = [
            parse_utc(term["due_at"])
            for term in document["terms"]
        ]
    except ValueError as exc:
        add("DATETIME_PARSE", str(exc))
    else:
        if created_at > valid_from:
            add(
                "AGREEMENT_TIME",
                "created_at must be <= valid_from.",
            )

        if valid_from >= valid_until:
            add(
                "AGREEMENT_TIME",
                "valid_from must be < valid_until.",
            )

        for index, due_at in enumerate(due_dates):
            if due_at < valid_from:
                add(
                    "TERM_DEADLINE",
                    f"/terms/{index}/due_at must be >= valid_from.",
                )

    payload = {
        key: value
        for key, value in document.items()
        if key != "agreement_digest"
    }

    try:
        canonical_bytes = rfc8785.dumps(payload)
    except rfc8785.CanonicalizationError as exc:
        add("CANONICALIZATION", str(exc))
    else:
        calculated_digest = (
            "sha256:"
            + hashlib.sha256(canonical_bytes).hexdigest()
        )

        if document["agreement_digest"] != calculated_digest:
            add(
                "DIGEST_MISMATCH",
                "Stored digest does not match agreement content. "
                f"Calculated: {calculated_digest}",
            )

    return issues


def validate_acceptance(record, agreement):
    """Compare an acceptance with one valid, unambiguous agreement."""
    issues = []

    if (
        record["agreement"]["agreement_digest"]
        != agreement["agreement_digest"]
    ):
        issues.append(
            (
                "ACCEPTANCE_DIGEST_MISMATCH",
                "Acceptance digest does not match "
                "the referenced agreement.",
            )
        )

    if record["party_id"] not in agreement["parties"]:
        issues.append(
            (
                "ACCEPTANCE_PARTY_NOT_FOUND",
                "Acceptance party_id is not in agreement parties.",
            )
        )

    try:
        accepted_at = parse_utc(record["accepted_at"])
        created_at = parse_utc(agreement["created_at"])
        valid_until = parse_utc(agreement["valid_until"])
    except ValueError as exc:
        issues.append(("DATETIME_PARSE", str(exc)))
    else:
        if not created_at <= accepted_at < valid_until:
            issues.append(
                (
                    "ACCEPTANCE_TIME",
                    "accepted_at must satisfy "
                    "created_at <= accepted_at < valid_until.",
                )
            )

    return issues


def extract_records(document):
    if not isinstance(document, dict):
        raise ValueError("Input must be a JSON object.")

    if "records" not in document:
        # Preserve support for standalone records.
        return [document]

    if set(document) != {"records"}:
        raise ValueError(
            "A record-set container must contain only records."
        )

    records = document["records"]

    if not isinstance(records, list) or not records:
        raise ValueError("records must be a non-empty array.")

    return records


def validate_document(document, validators):
    try:
        records = extract_records(document)
    except ValueError as exc:
        return [("INPUT_ERROR", str(exc))]

    issues = []
    invalid_indices = set()

    def append_at(index, found):
        if found:
            invalid_indices.add(index)

        for code, message in found:
            issues.append((code, f"record[{index}] {message}"))

    def add(index, code, message):
        append_at(index, [(code, message)])

    # Validate structures before accessing fields.
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            add(index, "SCHEMA", "Record must be an object.")
            continue

        record_type = record.get("record_type")

        if (
            not isinstance(record_type, str)
            or record_type not in validators
        ):
            add(
                index,
                "SCHEMA",
                "Missing or unsupported record_type.",
            )
            continue

        append_at(
            index,
            schema_issues(record, validators[record_type]),
        )

    if issues:
        return issues

    # Build complete indexes before resolving any references.
    agreements = {}
    acceptances = {}
    party_acceptances = {}
    commitments = {}
    term_commitments = {}

    for index, record in enumerate(records):
        record_type = record["record_type"]

        if record_type == "reciprocity_agreement":
            key = agreement_key(record)
            agreements.setdefault(key, []).append(index)

        elif record_type == "agreement_acceptance":
            acceptance_id = record["acceptance_id"]
            acceptances.setdefault(acceptance_id, []).append(index)

            key = (
                *agreement_key(record["agreement"]),
                record["party_id"],
            )
            party_acceptances.setdefault(key, []).append(index)

        elif record_type == "return_commitment":
            commitment_id = record["commitment_id"]
            commitments.setdefault(commitment_id, []).append(index)

            key = (
                *agreement_key(record["agreement"]),
                record["term_id"],
            )
            term_commitments.setdefault(key, []).append(index)

    def reject_duplicates(groups, code, message):
        for indices in groups.values():
            if len(indices) > 1:
                for index in indices:
                    add(index, code, message)

    # Mark every member of a duplicate group as invalid.
    reject_duplicates(
        agreements,
        "DUPLICATE_AGREEMENT",
        "agreement_id and agreement_version must be unique.",
    )
    reject_duplicates(
        acceptances,
        "DUPLICATE_ACCEPTANCE_ID",
        "acceptance_id duplicates another acceptance.",
    )
    reject_duplicates(
        party_acceptances,
        "DUPLICATE_PARTY_ACCEPTANCE",
        "The same party has multiple acceptances "
        "for the same agreement version.",
    )
    reject_duplicates(
        commitments,
        "DUPLICATE_COMMITMENT_ID",
        "commitment_id duplicates another commitment.",
    )
    reject_duplicates(
        term_commitments,
        "DUPLICATE_TERM_COMMITMENT",
        "The same agreement version and term "
        "have multiple commitments.",
    )

    # Validate all agreements before acceptances or commitments.
    for indices in agreements.values():
        for index in indices:
            append_at(index, validate_agreement(records[index]))

    def resolve_agreement(index, reference):
        candidates = agreements.get(agreement_key(reference), [])

        if not candidates:
            add(
                index,
                "MISSING_AGREEMENT",
                "No agreement matches the referenced ID and version.",
            )
            return None

        if len(candidates) != 1:
            add(
                index,
                "AMBIGUOUS_AGREEMENT",
                "Multiple agreements match "
                "the referenced ID and version.",
            )
            return None

        agreement_index = candidates[0]

        if agreement_index in invalid_indices:
            add(
                index,
                "INVALID_REFERENCED_AGREEMENT",
                "The referenced agreement failed validation.",
            )
            return None

        return records[agreement_index]

    # Finish validating every acceptance before using it for activation.
    for index, record in enumerate(records):
        if record["record_type"] != "agreement_acceptance":
            continue

        agreement = resolve_agreement(index, record["agreement"])

        if agreement is not None:
            append_at(
                index,
                validate_acceptance(record, agreement),
            )

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
                "Commitment digest does not match "
                "the referenced agreement.",
            )
            continue

        matching_terms = [
            term
            for term in agreement["terms"]
            if term["term_id"] == record["term_id"]
        ]

        if not matching_terms:
            add(
                index,
                "MISSING_TERM",
                "term_id is not in the referenced agreement.",
            )
            continue

        # A validated agreement guarantees term_id uniqueness.
        term = matching_terms[0]
        selected_acceptances = []

        for acceptance_id in record["acceptance_ids"]:
            candidates = acceptances.get(acceptance_id, [])

            if not candidates:
                add(
                    index,
                    "MISSING_ACCEPTANCE",
                    f"Acceptance not found: {acceptance_id}",
                )
                continue

            if len(candidates) != 1:
                add(
                    index,
                    "AMBIGUOUS_ACCEPTANCE",
                    f"Acceptance ID is not unique: {acceptance_id}",
                )
                continue

            acceptance_index = candidates[0]

            if acceptance_index in invalid_indices:
                add(
                    index,
                    "INVALID_REFERENCED_ACCEPTANCE",
                    f"Acceptance failed validation: {acceptance_id}",
                )
                continue

            acceptance = records[acceptance_index]

            # Schemas require the same three reference fields.
            if acceptance["agreement"] != reference:
                add(
                    index,
                    "COMMITMENT_ACCEPTANCE_BINDING",
                    "Referenced acceptance targets "
                    f"a different agreement: {acceptance_id}",
                )
                continue

            selected_acceptances.append(acceptance)

        accepted_parties = [
            acceptance["party_id"]
            for acceptance in selected_acceptances
        ]
        required_parties = set(agreement["parties"])

        if (
            len(selected_acceptances) != len(record["acceptance_ids"])
            or len(accepted_parties) != len(set(accepted_parties))
            or set(accepted_parties) != required_parties
        ):
            add(
                index,
                "CONSENT_INCOMPLETE",
                "acceptance_ids must resolve to exactly one "
                "valid acceptance from each agreement party.",
            )

        try:
            activated_at = parse_utc(record["activated_at"])
            valid_from = parse_utc(agreement["valid_from"])
            valid_until = parse_utc(agreement["valid_until"])
            due_at = parse_utc(term["due_at"])

            accepted_dates = [
                parse_utc(acceptance["accepted_at"])
                for acceptance in selected_acceptances
            ]
        except ValueError as exc:
            add(index, "DATETIME_PARSE", str(exc))
        else:
            if not valid_from <= activated_at < valid_until:
                add(
                    index,
                    "ACTIVATION_TIME",
                    "activated_at must satisfy "
                    "valid_from <= activated_at < valid_until.",
                )

            if activated_at > due_at:
                add(
                    index,
                    "ACTIVATION_AFTER_DEADLINE",
                    "activated_at must be <= term due_at.",
                )

            if any(
                accepted_at > activated_at
                for accepted_at in accepted_dates
            ):
                add(
                    index,
                    "ACCEPTANCE_AFTER_ACTIVATION",
                    "Every referenced acceptance must occur "
                    "at or before activated_at.",
                )

        trigger = term["trigger"]

        if trigger["type"] == "unconditional":
            expected_actor = term["provider_id"]
        else:
            expected_actor = trigger["verifier_party_id"]

        if record["activation"]["attested_by"] != expected_actor:
            add(
                index,
                "ACTIVATION_ACTOR",
                "activation.attested_by does not match "
                "the actor required by the term trigger.",
            )

    # Agreements and partial consent remain valid without commitments.
    # Commitment validity does not imply fulfillment or external trust.
    return issues


def validate_file(path: Path, validators):
    try:
        document = read_json(path)
    except (OSError, ValueError, UnicodeError) as exc:
        return [("INPUT_ERROR", str(exc))]

    return validate_document(document, validators)


def print_issues(issues):
    for code, message in issues:
        print(f"  {code}: {message}")


def run_examples(validators) -> int:
    matched_count = 0

    for relative_path, expected_codes in EXPECTED_CASES.items():
        issues = validate_file(ROOT / relative_path, validators)
        actual_codes = {code for code, _ in issues}
        matched = actual_codes == expected_codes

        if matched:
            matched_count += 1

        label = "PASS" if matched else "FAIL"

        print(
            f"[{label}] {relative_path} "
            f"codes={sorted(actual_codes)}"
        )

        if not matched:
            print(f"  Expected: {sorted(expected_codes)}")
            print_issues(issues)

    total = len(EXPECTED_CASES)

    print(
        f"{matched_count}/{total} scenarios "
        "matched expected results."
    )

    return 0 if matched_count == total else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate ACRP agreements, acceptances, "
            "and return commitments."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help=(
            "Validate one JSON record or record-set file. "
            "Relative paths are resolved from the repository root."
        ),
    )
    args = parser.parse_args()

    format_checker = FormatChecker()

    for required_format in ("uri", "date-time"):
        if required_format not in format_checker.checkers:
            print(
                f"Missing format support: {required_format}. "
                "Install dependencies from requirements.txt.",
                file=sys.stderr,
            )
            return 2

    validators = {}

    for record_type, relative_path in SCHEMA_PATHS.items():
        try:
            schema = read_json(ROOT / relative_path)
            Draft202012Validator.check_schema(schema)
        except (OSError, ValueError, UnicodeError, SchemaError) as exc:
            print(
                f"Schema setup failed ({relative_path}): {exc}",
                file=sys.stderr,
            )
            return 2

        validators[record_type] = Draft202012Validator(
            schema,
            format_checker=format_checker,
        )

    if args.dataset is None:
        return run_examples(validators)

    path = args.dataset

    if not path.is_absolute():
        path = ROOT / path

    issues = validate_file(path, validators)
    codes = sorted({code for code, _ in issues})

    if issues:
        print(f"[INVALID] {args.dataset} codes={codes}")
        print_issues(issues)
        return 1

    print(f"[VALID] {args.dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
