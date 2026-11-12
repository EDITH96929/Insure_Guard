
import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect, text

# Make src directory importable
SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_DIR))

from database.connection import engine


SCHEMA = "insureguard"


def get_active_employees(connection):
    """Return active employees using the available status column."""

    inspector = inspect(engine)

    columns = {
        column["name"]
        for column in inspector.get_columns(
            "employees",
            schema=SCHEMA
        )
    }

    if "is_active" in columns:
        query = text("""
            SELECT employee_id
            FROM insureguard.employees
            WHERE is_active = TRUE
            ORDER BY employee_id
        """)

    else:
        status_column = next(
            (
                column
                for column in (
                    "employment_status",
                    "employee_status",
                    "status"
                )
                if column in columns
            ),
            None
        )

        if not status_column:
            raise RuntimeError(
                "Could not identify the employee active-status column."
            )

        query = text(f"""
            SELECT employee_id
            FROM insureguard.employees
            WHERE UPPER({status_column}) = 'ACTIVE'
            ORDER BY employee_id
        """)

    return connection.execute(query).scalars().all()


def list_actions():
    """Display remediation actions and their current verification status."""

    query = text("""
        SELECT
            ra.action_id,
            ra.exception_id,
            e.exception_type,
            e.severity,
            ra.owner_id,
            ra.action_status,
            ra.due_date,
            ra.completion_date,

            (
                SELECT rv.verification_status
                FROM insureguard.remediation_verifications rv
                WHERE rv.action_id = ra.action_id
                ORDER BY rv.verification_id DESC
                LIMIT 1
            ) AS latest_verification

        FROM insureguard.remediation_actions ra

        JOIN insureguard.exceptions e
            ON e.exception_id = ra.exception_id

        ORDER BY
            CASE ra.action_status
                WHEN 'PENDING_VERIFICATION' THEN 1
                WHEN 'IN_PROGRESS' THEN 2
                WHEN 'OPEN' THEN 3
                WHEN 'OVERDUE' THEN 4
                WHEN 'COMPLETED' THEN 5
                ELSE 6
            END,
            ra.action_id
    """)

    with engine.connect() as connection:
        actions = connection.execute(query).mappings().all()

    print("\nINSUREGUARD — REMEDIATION REGISTER")
    print("-" * 110)

    if not actions:
        print("No remediation actions found.")
        return

    for action in actions:
        print(
            f"Action: {action['action_id']} | "
            f"Exception: {action['exception_id']} | "
            f"Type: {action['exception_type']} | "
            f"Severity: {action['severity']} | "
            f"Owner: {action['owner_id']} | "
            f"Status: {action['action_status']} | "
            f"Verification: {action['latest_verification'] or 'NOT STARTED'}"
        )

    print("-" * 110)
    print(f"Total remediation actions: {len(actions)}")


def start_action(action_id):
    """Move an OPEN remediation action into IN_PROGRESS."""

    with engine.begin() as connection:

        result = connection.execute(
            text("""
                UPDATE insureguard.remediation_actions
                SET action_status = 'IN_PROGRESS'
                WHERE action_id = :action_id
                  AND action_status = 'OPEN'
            """),
            {"action_id": action_id}
        )

        if result.rowcount != 1:
            raise RuntimeError(
                "Action not found or action is not currently OPEN."
            )

    print(f"\nRemediation action {action_id} is now IN_PROGRESS.")


def submit_for_verification(action_id):
    """
    Submit an IN_PROGRESS action for independent verification.
    The owner selects an independent reviewer from active employees.
    """

    with engine.begin() as connection:

        action = connection.execute(
            text("""
                SELECT
                    action_id,
                    owner_id,
                    action_status,
                    action_description
                FROM insureguard.remediation_actions
                WHERE action_id = :action_id
                FOR UPDATE
            """),
            {"action_id": action_id}
        ).mappings().first()

        if not action:
            raise RuntimeError("Remediation action not found.")

        if action["action_status"] != "IN_PROGRESS":
            raise RuntimeError(
                "Only IN_PROGRESS actions can be submitted for verification."
            )

        owner_id = action["owner_id"]

        employees = get_active_employees(connection)

        reviewers = [
            employee_id
            for employee_id in employees
            if employee_id != owner_id
        ]

        if not reviewers:
            raise RuntimeError(
                "No independent active reviewer is available."
            )

        print("\nREMEDIATION ACTION")
        print("-" * 55)
        print("Action ID:", action["action_id"])
        print("Owner:", owner_id)
        print("Description:", action["action_description"])

        print("\nAVAILABLE INDEPENDENT REVIEWERS")
        for index, employee_id in enumerate(reviewers, start=1):
            print(f"{index}. {employee_id}")

        choice = input(
            "\nSelect reviewer number: "
        ).strip()

        if not choice.isdigit():
            raise RuntimeError("Invalid reviewer selection.")

        reviewer_index = int(choice) - 1

        if reviewer_index < 0 or reviewer_index >= len(reviewers):
            raise RuntimeError("Reviewer selection is out of range.")

        reviewer_id = reviewers[reviewer_index]

        print("\nSelected reviewer:", reviewer_id)

        confirmation = input(
            "Submit this action for verification? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":
            print("Submission cancelled. No changes made.")
            return

        # Record the owner's completion submission.
        connection.execute(
            text("""
                UPDATE insureguard.remediation_actions
                SET
                    action_status = 'PENDING_VERIFICATION',
                    completion_date = CURRENT_DATE
                WHERE action_id = :action_id
            """),
            {"action_id": action_id}
        )

        # Create a separate verification attempt.
        connection.execute(
            text("""
                INSERT INTO insureguard.remediation_verifications (
                    action_id,
                    reviewer_id,
                    verification_status
                )
                VALUES (
                    :action_id,
                    :reviewer_id,
                    'PENDING'
                )
            """),
            {
                "action_id": action_id,
                "reviewer_id": reviewer_id
            }
        )

    print("\nACTION SUBMITTED SUCCESSFULLY")
    print("Action ID:", action_id)
    print("Owner:", owner_id)
    print("Reviewer:", reviewer_id)
    print("Status: PENDING_VERIFICATION")


def review_action(action_id):
    """Allow the assigned independent reviewer to verify an action."""

    with engine.begin() as connection:

        verification = connection.execute(
            text("""
                SELECT
                    rv.verification_id,
                    rv.action_id,
                    rv.reviewer_id,
                    rv.verification_status,
                    ra.owner_id,
                    ra.action_status,
                    ra.action_description,
                    ra.completion_date,
                    e.exception_type,
                    e.severity

                FROM insureguard.remediation_verifications rv

                JOIN insureguard.remediation_actions ra
                    ON ra.action_id = rv.action_id

                JOIN insureguard.exceptions e
                    ON e.exception_id = ra.exception_id

                WHERE rv.action_id = :action_id
                  AND rv.verification_status = 'PENDING'

                ORDER BY rv.verification_id DESC
                LIMIT 1
                FOR UPDATE OF rv, ra
            """),
            {"action_id": action_id}
        ).mappings().first()

        if not verification:
            raise RuntimeError(
                "No pending verification exists for this action."
            )

        print("\nINSUREGUARD — INDEPENDENT VERIFICATION")
        print("=" * 55)
        print("Action ID:", verification["action_id"])
        print("Exception Type:", verification["exception_type"])
        print("Severity:", verification["severity"])
        print("Action Owner:", verification["owner_id"])
        print("Assigned Reviewer:", verification["reviewer_id"])
        print("Action Status:", verification["action_status"])
        print("Completion Date:", verification["completion_date"])
        print("Action Description:", verification["action_description"])
        print("=" * 55)

        print("\nReviewer ID must match the assigned reviewer.")

        reviewer_id = input("Enter your reviewer ID: ").strip()

        if reviewer_id != verification["reviewer_id"]:
            raise RuntimeError(
                "Only the assigned reviewer can complete this verification."
            )

        if reviewer_id == verification["owner_id"]:
            raise RuntimeError(
                "The remediation owner cannot verify their own action."
            )

        print("\nChoose verification decision:")
        print("1. APPROVED")
        print("2. REJECTED")
        print("3. NEEDS_MORE_EVIDENCE")

        choices = {
            "1": "APPROVED",
            "2": "REJECTED",
            "3": "NEEDS_MORE_EVIDENCE"
        }

        choice = input("Enter choice (1-3): ").strip()

        if choice not in choices:
            raise RuntimeError("Invalid verification decision.")

        decision = choices[choice]

        notes = input(
            "\nEnter verification findings and notes: "
        ).strip()

        evidence = input(
            "Enter evidence reference: "
        ).strip()

        if not notes or not evidence:
            raise RuntimeError(
                "Verification notes and evidence reference are required."
            )

        confirmation = input(
            f"\nConfirm verification decision {decision}? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":
            print("Verification cancelled. No changes made.")
            return

        # Save the independent review decision.
        connection.execute(
            text("""
                UPDATE insureguard.remediation_verifications
                SET
                    verification_status = :decision,
                    verification_notes = :notes,
                    evidence_reference = :evidence,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE verification_id = :verification_id
                  AND verification_status = 'PENDING'
            """),
            {
                "decision": decision,
                "notes": notes,
                "evidence": evidence,
                "verification_id": verification["verification_id"]
            }
        )

        # Update the remediation action according to the decision.
        if decision == "APPROVED":

            new_action_status = "COMPLETED"

        else:

            new_action_status = "IN_PROGRESS"

        connection.execute(
            text("""
                UPDATE insureguard.remediation_actions
                SET action_status = :new_status
                WHERE action_id = :action_id
            """),
            {
                "new_status": new_action_status,
                "action_id": action_id
            }
        )

    print("\nVERIFICATION SAVED SUCCESSFULLY")
    print("-" * 50)
    print("Action ID:", action_id)
    print("Verification Decision:", decision)
    print("New Remediation Status:", new_action_status)
    print("-" * 50)


def main():

    parser = argparse.ArgumentParser(
        description="InsureGuard Remediation Verification Engine"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List remediation actions."
    )

    parser.add_argument(
        "--start",
        type=int,
        help="Start work on an OPEN remediation action."
    )

    parser.add_argument(
        "--submit",
        type=int,
        help="Submit an IN_PROGRESS action for verification."
    )

    parser.add_argument(
        "--review",
        type=int,
        help="Review a pending verification by action ID."
    )

    args = parser.parse_args()

    selected_commands = sum([
        args.list,
        args.start is not None,
        args.submit is not None,
        args.review is not None
    ])

    if selected_commands != 1:
        parser.print_help()
        return

    if args.list:
        list_actions()

    elif args.start is not None:
        start_action(args.start)

    elif args.submit is not None:
        submit_for_verification(args.submit)

    elif args.review is not None:
        review_action(args.review)


if __name__ == "__main__":

    try:
        main()

    except Exception as error:
        print("\nREMEDIATION VERIFICATION FAILED")
        print(error)
        raise
