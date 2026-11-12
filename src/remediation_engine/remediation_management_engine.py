
"""
InsureGuard - Remediation Management Engine

Purpose:
    Assign unresolved control exceptions to active employees
    and create corrective-action records.

Modes:
    PREVIEW       - Display proposed assignments without changes.
    --apply       - Save assignments to PostgreSQL.

Important:
    - PostgreSQL automatically generates action_id.
    - Only active employees are assigned.
    - Existing remediation actions are not duplicated.
    - All inserts happen in one database transaction.
    - Assignments are synthetic and require management review.
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

# --------------------------------------------------
# PROJECT IMPORTS
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

from database.connection import engine


# --------------------------------------------------
# 1. GET LATEST COMPLETED CONTROL TEST RUN
# --------------------------------------------------

LATEST_RUN_SQL = text("""
    SELECT MAX(run_id)
    FROM insureguard.control_test_runs
    WHERE run_status = 'COMPLETED'
""")


# --------------------------------------------------
# 2. GET ACTIVE EMPLOYEES
# --------------------------------------------------

ACTIVE_EMPLOYEES_SQL = text("""
    SELECT employee_id
    FROM insureguard.employees
    WHERE employee_status = 'ACTIVE'
    ORDER BY employee_id
""")


# --------------------------------------------------
# 3. FIND EXCEPTIONS NEEDING REMEDIATION
# --------------------------------------------------

PENDING_EXCEPTIONS_SQL = text("""
    SELECT
        e.exception_id,
        e.severity,
        ct.control_id,
        ct.claim_id,
        ct.payment_id

    FROM insureguard.exceptions e

    JOIN insureguard.control_tests ct
        ON ct.test_id = e.test_id

    WHERE ct.run_id = :run_id
      AND ct.test_result = 'FAIL'
      AND e.investigation_status = 'OPEN'

      AND NOT EXISTS (
          SELECT 1
          FROM insureguard.remediation_actions ra
          WHERE ra.exception_id = e.exception_id
      )

    ORDER BY
        CASE e.severity
            WHEN 'CRITICAL' THEN 1
            WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3
            WHEN 'LOW' THEN 4
            ELSE 5
        END,
        e.exception_id
""")


# --------------------------------------------------
# 4. INSERT REMEDIATION ACTION
#
# IMPORTANT:
# action_id is omitted because PostgreSQL generates it.
# --------------------------------------------------

INSERT_ACTION_SQL = text("""
    INSERT INTO insureguard.remediation_actions (
        exception_id,
        owner_id,
        action_description,
        due_date,
        action_status
    )

    VALUES (
        :exception_id,
        :owner_id,
        :action_description,
        :due_date,
        'OPEN'
    )

    RETURNING action_id
""")


# --------------------------------------------------
# 5. REMEDIATION SUMMARY
# --------------------------------------------------

SUMMARY_SQL = text("""
    SELECT
        ra.action_status,

        COUNT(*) AS total_actions,

        COUNT(*) FILTER (
            WHERE ra.due_date < CURRENT_DATE
              AND ra.action_status <> 'COMPLETED'
        ) AS past_due_actions

    FROM insureguard.remediation_actions ra

    JOIN insureguard.exceptions e
        ON e.exception_id = ra.exception_id

    JOIN insureguard.control_tests ct
        ON ct.test_id = e.test_id

    WHERE ct.run_id = :run_id

    GROUP BY ra.action_status

    ORDER BY ra.action_status
""")


# --------------------------------------------------
# 6. CONTROL-SPECIFIC CORRECTIVE ACTION DESCRIPTIONS
# --------------------------------------------------

ACTION_DESCRIPTIONS = {

    "CT-001": (
        "Investigate missing or invalid payment authorization. "
        "Review approval evidence, confirm authorization "
        "authority, and document the required corrective action."
    ),

    "CT-002": (
        "Investigate potential duplicate payment. Compare "
        "payment references and settlement records, confirm "
        "whether the transactions are legitimate, and document "
        "any required recovery or correction."
    ),

    "CT-003": (
        "Investigate settlement amounts exceeding approval. "
        "Reconcile successful payments against approved amounts, "
        "review authorized adjustments, and document the resolution."
    )
}


# --------------------------------------------------
# 7. DUE DATE RULES
# --------------------------------------------------

DUE_DAYS = {
    "CRITICAL": 7,
    "HIGH": 14,
    "MEDIUM": 21,
    "LOW": 30
}


# --------------------------------------------------
# 8. DISPLAY REMEDIATION SUMMARY
# --------------------------------------------------

def show_summary(connection, run_id):

    rows = connection.execute(
        SUMMARY_SQL,
        {"run_id": run_id}
    ).mappings().all()

    print("\nREMEDIATION STATUS SUMMARY")
    print("-" * 65)

    if not rows:
        print("No remediation actions found.")
        return

    total_actions = 0
    total_overdue = 0

    for row in rows:

        total_actions += row["total_actions"]
        total_overdue += row["past_due_actions"]

        print(
            f"{row['action_status']:<22} "
            f"Actions: {row['total_actions']:<5} "
            f"Past due: {row['past_due_actions']}"
        )

    print("-" * 65)
    print(f"Total actions : {total_actions}")
    print(f"Past due      : {total_overdue}")


# --------------------------------------------------
# 9. MAIN REMEDIATION ENGINE
# --------------------------------------------------

def run_remediation_engine(apply_changes=False):

    print("=" * 65)
    print("       INSUREGUARD REMEDIATION MANAGEMENT ENGINE")
    print("=" * 65)

    mode = "APPLY" if apply_changes else "PREVIEW"

    print(f"\nExecution Mode: {mode}")

    try:

        with engine.begin() as connection:

            # Prevent two instances of this engine from
            # assigning the same exceptions concurrently.
            if apply_changes:

                connection.execute(
                    text("SELECT pg_advisory_xact_lock(726301)")
                )

            # ------------------------------------------
            # GET LATEST COMPLETED TEST RUN
            # ------------------------------------------

            run_id = connection.execute(
                LATEST_RUN_SQL
            ).scalar_one_or_none()

            if run_id is None:

                print("\nNo completed control test run found.")
                return

            # ------------------------------------------
            # GET ACTIVE EMPLOYEES
            # ------------------------------------------

            employees = connection.execute(
                ACTIVE_EMPLOYEES_SQL
            ).scalars().all()

            if not employees:

                print("\nNo active employees available.")
                return

            # ------------------------------------------
            # GET UNASSIGNED EXCEPTIONS
            # ------------------------------------------

            exceptions = connection.execute(
                PENDING_EXCEPTIONS_SQL,
                {"run_id": run_id}
            ).mappings().all()

            print(f"\nControl Test Run ID : {run_id}")
            print(f"Active Employees    : {len(employees)}")
            print(f"Unassigned Exceptions: {len(exceptions)}")

            if not exceptions:

                print("\nNo new remediation assignments required.")

                if apply_changes:
                    show_summary(connection, run_id)

                return

            # ------------------------------------------
            # PREPARE ASSIGNMENTS
            # ------------------------------------------

            today = date.today()

            created = 0

            severity_counts = {}

            print("\nPROPOSED REMEDIATION ASSIGNMENTS")
            print("-" * 65)

            for index, exception in enumerate(exceptions):

                # Round-robin assignment among active employees.
                # These are demonstration assignments.
                owner_id = employees[index % len(employees)]

                severity = (
                    exception["severity"] or "MEDIUM"
                ).upper()

                due_days = DUE_DAYS.get(severity, 30)

                due_date = today + timedelta(days=due_days)

                description = ACTION_DESCRIPTIONS.get(
                    exception["control_id"],
                    "Investigate the exception, identify its root "
                    "cause, and document the corrective action."
                )

                print(
                    f"Exception: {exception['exception_id']} | "
                    f"Control: {exception['control_id']} | "
                    f"Severity: {severity} | "
                    f"Owner: {owner_id} | "
                    f"Due: {due_date}"
                )

                severity_counts[severity] = (
                    severity_counts.get(severity, 0) + 1
                )

                # --------------------------------------
                # SAVE TO DATABASE ONLY IN APPLY MODE
                # --------------------------------------

                if apply_changes:

                    action_id = connection.execute(
                        INSERT_ACTION_SQL,
                        {
                            "exception_id": exception["exception_id"],
                            "owner_id": owner_id,
                            "action_description": description,
                            "due_date": due_date
                        }
                    ).scalar_one()

                    created += 1

            # ------------------------------------------
            # EXECUTION SUMMARY
            # ------------------------------------------

            print("\n" + "-" * 65)
            print("ASSIGNMENT BREAKDOWN")

            for severity, count in sorted(severity_counts.items()):
                print(f"{severity:<15}: {count}")

            if apply_changes:

                print(f"\nActions Created: {created}")

                show_summary(connection, run_id)

            else:

                print("\nPREVIEW MODE")
                print("No database records were inserted.")
                print(
                    "Review the proposed assignments before "
                    "running with --apply."
                )

        # Transaction commits automatically if successful.

        print("\n" + "=" * 65)

        if apply_changes:
            print("REMEDIATION ASSIGNMENTS SAVED SUCCESSFULLY")
            print("Database Transaction: COMMITTED")
        else:
            print("REMEDIATION PREVIEW COMPLETED")
            print("Database Transaction: READ ONLY")

        print("=" * 65)

    except Exception as error:

        print("\nREMEDIATION ENGINE FAILED")
        print("Database transaction rolled back.")
        print("Error:", error)

        raise


# --------------------------------------------------
# 10. PROGRAM ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="InsureGuard Remediation Management Engine"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Save proposed remediation assignments to PostgreSQL"
    )

    args = parser.parse_args()

    run_remediation_engine(
        apply_changes=args.apply
    )
