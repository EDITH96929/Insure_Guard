
import argparse
import sys
import json
from pathlib import Path

from sqlalchemy import text

# Make the src directory importable
SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_DIR))

from database.connection import engine


def list_cases():
    """Display all investigation cases."""

    query = text("""
        SELECT
            ir.investigation_id,
            ir.exception_id,
            e.exception_type,
            e.severity,
            ir.investigator_id,
            ir.investigation_status,
            ir.created_at
        FROM insureguard.investigation_records ir
        JOIN insureguard.exceptions e
            ON e.exception_id = ir.exception_id
        ORDER BY
            CASE e.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                ELSE 4
            END,
            ir.investigation_id
    """)

    with engine.connect() as connection:
        cases = connection.execute(query).mappings().all()

    print("\nINSUREGUARD — INVESTIGATION CASE REGISTER")
    print("-" * 90)

    if not cases:
        print("No investigation cases found.")
        return

    for case in cases:
        print(
            f"Case ID: {case['investigation_id']} | "
            f"Exception: {case['exception_id']} | "
            f"Type: {case['exception_type']} | "
            f"Severity: {case['severity']} | "
            f"Status: {case['investigation_status']} | "
            f"Investigator: {case['investigator_id']}"
        )

    print("-" * 90)
    print(f"Total investigation cases: {len(cases)}")


def get_case_details(connection, case_id):
    """Retrieve investigation, exception and transaction details."""

    query = text("""
        SELECT
            ir.investigation_id,
            ir.exception_id,
            ir.investigator_id,
            ir.investigation_status,
            ir.findings,
            ir.root_cause,
            ir.evidence_reference,
            ir.recommended_action,

            e.exception_type,
            e.severity,
            e.detected_at,
            e.analyst_notes,

            ct.test_id,
            ct.control_id,
            ct.test_result,
            ct.evidence AS test_evidence,
            ct.tested_at,

            cl.control_name,
            cl.control_description,

            c.claim_id,
            c.claim_type,
            c.requested_amount,
            c.claim_status,

            p.payment_id,
            p.payment_reference,
            p.payment_amount,
            p.payment_status,
            p.payment_date,

            a.approval_id,
            a.approval_status,
            a.approved_amount,
            a.approver_id,
            a.approval_timestamp

        FROM insureguard.investigation_records ir

        JOIN insureguard.exceptions e
            ON e.exception_id = ir.exception_id

        JOIN insureguard.control_tests ct
            ON ct.test_id = e.test_id

        LEFT JOIN insureguard.control_library cl
            ON cl.control_id = ct.control_id

        LEFT JOIN insureguard.claims c
            ON c.claim_id = ct.claim_id

        LEFT JOIN insureguard.payments p
            ON p.payment_id = ct.payment_id

        LEFT JOIN insureguard.claim_approvals a
            ON a.approval_id = p.approval_id

        WHERE ir.investigation_id = :case_id
    """)

    return connection.execute(
        query,
        {"case_id": case_id}
    ).mappings().first()


def display_case(case):
    """Display all available case and transaction information."""

    print("\nINSUREGUARD — CASE INVESTIGATION")
    print("=" * 60)

    fields = [
        ("Investigation ID", "investigation_id"),
        ("Exception ID", "exception_id"),
        ("Investigator", "investigator_id"),
        ("Investigation Status", "investigation_status"),
        ("Exception Type", "exception_type"),
        ("Severity", "severity"),
        ("Detected At", "detected_at"),
        ("Control ID", "control_id"),
        ("Control Name", "control_name"),
        ("Control Description", "control_description"),
        ("Test Result", "test_result"),
        ("Claim ID", "claim_id"),
        ("Claim Type", "claim_type"),
        ("Requested Amount", "requested_amount"),
        ("Claim Status", "claim_status"),
        ("Payment ID", "payment_id"),
        ("Payment Reference", "payment_reference"),
        ("Payment Amount", "payment_amount"),
        ("Payment Status", "payment_status"),
        ("Payment Date", "payment_date"),
        ("Approval ID", "approval_id"),
        ("Approval Status", "approval_status"),
        ("Approved Amount", "approved_amount"),
        ("Approver ID", "approver_id"),
        ("Approval Timestamp", "approval_timestamp"),
    ]

    for label, key in fields:
        print(f"{label:24}: {case[key]}")

    print("\nCONTROL TEST EVIDENCE")

    evidence = case["test_evidence"]

    if isinstance(evidence, (dict, list)):
        print(json.dumps(evidence, indent=2, default=str))
    else:
        print(evidence)

    print("\nPREVIOUS INVESTIGATION NOTES")
    print("Findings:", case["findings"] or "Not recorded")
    print("Root Cause:", case["root_cause"] or "Not recorded")
    print("Evidence Reference:", case["evidence_reference"] or "Not recorded")
    print("Recommended Action:", case["recommended_action"] or "Not recorded")

    print("=" * 60)


def review_case(case_id):
    """Allow an analyst to investigate and update a case."""

    with engine.connect() as connection:
        case = get_case_details(connection, case_id)

    if not case:
        print(f"Investigation case {case_id} was not found.")
        return

    if case["investigation_status"] in ("COMPLETED", "ESCALATED"):
        print(
            f"This case is already {case['investigation_status']}. "
            "It cannot be edited through this review workflow."
        )
        return

    display_case(case)

    print("\nRECORD INVESTIGATION")
    print("Review the transaction evidence before entering your conclusion.")

    findings = input("\nWhat did you find? ").strip()

    root_cause = input(
        "What is the likely root cause? "
    ).strip()

    evidence_reference = input(
        "Evidence reference (document/record ID, or description): "
    ).strip()

    recommended_action = input(
        "What action do you recommend? "
    ).strip()

    if not findings or not root_cause or not recommended_action:
        print(
            "\nFindings, root cause and recommended action are required. "
            "No changes were saved."
        )
        return

    print("\nChoose investigation outcome:")
    print("1. CONFIRMED_CONTROL_FAILURE")
    print("2. FALSE_POSITIVE")
    print("3. PENDING_EVIDENCE")
    print("4. ESCALATED")

    outcome_choices = {
        "1": "CONFIRMED_CONTROL_FAILURE",
        "2": "FALSE_POSITIVE",
        "3": "PENDING_EVIDENCE",
        "4": "ESCALATED",
    }

    choice = input("Enter choice (1-4): ").strip()

    if choice not in outcome_choices:
        print("Invalid choice. No changes were saved.")
        return

    outcome = outcome_choices[choice]

    if outcome == "ESCALATED":
        new_status = "ESCALATED"

    elif outcome == "PENDING_EVIDENCE":
        new_status = "IN_PROGRESS"

    else:
        new_status = "COMPLETED"

    confirmation = input(
        f"\nSave this investigation as {new_status}? (yes/no): "
    ).strip().lower()

    if confirmation != "yes":
        print("Cancelled. No changes were saved.")
        return

    # Separate parameters avoid PostgreSQL's ambiguous
    # parameter type inference for repeated status parameters.
    update_query = text("""
        UPDATE insureguard.investigation_records
        SET
            investigation_status = :status_value,
            investigation_outcome = :outcome,
            findings = :findings,
            root_cause = :root_cause,
            evidence_reference = :evidence_reference,
            recommended_action = :recommended_action,

            started_at = COALESCE(
                started_at,
                CURRENT_TIMESTAMP
            ),

            completed_at = CASE
                WHEN :is_terminal = TRUE
                    THEN CURRENT_TIMESTAMP
                ELSE NULL
            END,

            updated_at = CURRENT_TIMESTAMP

        WHERE investigation_id = :case_id
          AND investigation_status NOT IN (
              'COMPLETED',
              'ESCALATED'
          )
    """)

    parameters = {
        "case_id": case_id,
        "status_value": new_status,
        "is_terminal": new_status in ("COMPLETED", "ESCALATED"),
        "outcome": outcome,
        "findings": findings,
        "root_cause": root_cause,
        "evidence_reference": evidence_reference or None,
        "recommended_action": recommended_action,
    }

    with engine.begin() as connection:

        result = connection.execute(
            update_query,
            parameters
        )

        if result.rowcount != 1:
            raise RuntimeError(
                "The investigation was not updated. "
                "The case may have been completed or changed by another user."
            )

    print("\nINVESTIGATION SAVED SUCCESSFULLY")
    print("-" * 45)
    print("Investigation ID :", case_id)
    print("Exception Outcome:", outcome)
    print("Investigation Status:", new_status)
    print("-" * 45)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="InsureGuard Investigation Review Engine"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="Display investigation cases."
    )

    parser.add_argument(
        "--case",
        type=int,
        help="Open an investigation case using its ID."
    )

    args = parser.parse_args()

    try:

        if args.list:
            list_cases()

        elif args.case is not None:
            review_case(args.case)

        else:
            parser.print_help()

    except Exception as error:
        print("\nInvestigation review failed:")
        print(error)
        raise
