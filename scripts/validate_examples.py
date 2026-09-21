#!/usr/bin/env python3
"""Validate ACRP v0.1 agreement examples."""

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

SCHEMA_PATH = (
    ROOT / "schemas/reciprocity-agreement.schema.json"
)

# Each example is an independent validation case.
# Failure examples intentionally reuse identifiers from the valid example.
EXPECTED_CASES = {
    "examples/pass/reciprocity-agreement-basic.example.json": set(),
    "examples/fail/reciprocity-agreement-digest-mismatch.example.json": {
        "DIGEST_MISMATCH"
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


def validate_agreement(document, validator):
    issues = []

    def add(code: str, message: str):
        issues.append((code, message))

    schema_errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            json_pointer(error.absolute_path),
            error.message,
        ),
    )

    for error in schema_errors:
        add(
            "SCHEMA",
            f"{json_pointer(error.absolute_path)}: {error.message}",
        )

    # Do not access fields or calculate a digest on malformed records.
    if schema_errors:
        return issues

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


def validate_file(path: Path, validator):
    try:
        document = read_json(path)
    except (OSError, ValueError, UnicodeError) as exc:
        return [("INPUT_ERROR", str(exc))]

    return validate_agreement(document, validator)


def print_issues(issues):
    for code, message in issues:
        print(f"  {code}: {message}")


def run_examples(validator) -> int:
    matched_count = 0

    for relative_path, expected_codes in EXPECTED_CASES.items():
        issues = validate_file(ROOT / relative_path, validator)
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
        description="Validate ACRP v0.1 agreement records."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help=(
            "Validate one agreement JSON file. "
            "Relative paths are resolved from the repository root."
        ),
    )
    args = parser.parse_args()

    try:
        schema = read_json(SCHEMA_PATH)
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError, UnicodeError, SchemaError) as exc:
        print(f"Schema setup failed: {exc}", file=sys.stderr)
        return 2

    format_checker = FormatChecker()

    # Fail explicitly if required format support is unavailable.
    for required_format in ("uri", "date-time"):
        if required_format not in format_checker.checkers:
            print(
                f"Missing format support: {required_format}. "
                "Install dependencies from requirements.txt.",
                file=sys.stderr,
            )
            return 2

    validator = Draft202012Validator(
        schema,
        format_checker=format_checker,
    )

    if args.dataset is None:
        return run_examples(validator)

    path = args.dataset
    if not path.is_absolute():
        path = ROOT / path

    issues = validate_file(path, validator)
    codes = sorted({code for code, _ in issues})

    if issues:
        print(f"[INVALID] {args.dataset} codes={codes}")
        print_issues(issues)
        return 1

    print(f"[VALID] {args.dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
