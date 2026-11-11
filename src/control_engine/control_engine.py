
from pathlib import Path
import sys
import json

from sqlalchemy import text

# --------------------------------------------------
# PROJECT PATH AND DATABASE CONNECTION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"

sys.path.insert(0, str(SRC_DIR))

from database.connection import engine


# --------------------------------------------------
# CONTROL DEFINITIONS
# --------------------------------------------------

CONTROLS = {
    "CT-001": {
        "name": "Payment Authorization Verification",
        "description": (
            "Every payment must have a valid approved authorization."
        )
    },
    "CT-002": {
        "name": "Duplicate Payment Detection",
        "description": (
            "Identify repeated payment transactions."
        )
    }
}


# --------------------------------------------------
# CREATE TEST RUN
# --------------------------------------------------

def create_test_run(connection):

    result = connection.execute(
        text("""
            INSERT INTO insureguard.control_test_runs (
                run_name,
                executed_by,
                source_batch_id,
                run_status
            )
            VALUES (
                :run_name,
                :executed_by,
                :source_batch_id,
                'RUNNING'
            )
            RETURNING run_id
        """),
        {
            "run_name": "Initial Payment Control Testing",
            "executed_by": "InsureGuard Control Engine",
            "source_batch_id": "TRANSACTION-BATCH-001"
        }
    )

    return result.scalar_one()


# --------------------------------------------------
# LOAD PAYMENT RECORDS FOR CT-001
# --------------------------------------------------

def get_authorization_results(connection):

    return connection.execute(
        text("""
            SELECT
                p.payment_id,
                p.claim_id,
                p.approval_id,
                p.payment_amount,
                p.payment_reference,
                p.payment_status,
                a.approval_status

            FROM insureguard.payments p

            LEFT JOIN insureguard.claim_approvals a
                ON p.approval_id = a.approval_id
                AND p.claim_id = a.claim_id

            ORDER BY p.payment_id
        """)
    ).mappings().all()


# --------------------------------------------------
# LOAD PAYMENT RECORDS FOR CT-002
# --------------------------------------------------

def get_duplicate_results(connection):

    return connection.execute(
        text("""
            SELECT
                payment_id,
                claim_id,
                payment_reference,
                payment_amount,
                payment_status,
                duplicate_number

            FROM (
                SELECT
                    payment_id,
                    claim_id,
                    payment_reference,
                    payment_amount,
                    payment_status,

                    ROW_NUMBER() OVER (
                        PARTITION BY
                            claim_id,
                            payment_reference,
                            payment_amount,
                            payment_status

                        ORDER BY payment_id
                    ) AS duplicate_number

                FROM insureguard.payments

                WHERE payment_reference IS NOT NULL
            ) payment_records

            ORDER BY payment_id
        """)
    ).mappings().all()


# --------------------------------------------------
# SAVE TEST RESULT AND EXCEPTION
# --------------------------------------------------

def save_test_result(
    connection,
    run_id,
    control_id,
    claim_id,
    payment_id,
    result,
    evidence,
    severity
):

    test_result = connection.execute(
        text("""
            INSERT INTO insureguard.control_tests (
                run_id,
                control_id,
                claim_id,
                payment_id,
                test_result,
                evidence
            )
            VALUES (
                :run_id,
                :control_id,
                :claim_id,
                :payment_id,
                :test_result,
                CAST(:evidence AS JSONB)
            )
            RETURNING test_id
        """),
        {
            "run_id": run_id,
            "control_id": control_id,
            "claim_id": claim_id,
            "payment_id": payment_id,
            "test_result": result,
            "evidence": json.dumps(evidence)
        }
    )

    test_id = test_result.scalar_one()

    if result == "FAIL":

        connection.execute(
            text("""
                INSERT INTO insureguard.exceptions (
                    test_id,
                    exception_type,
                    severity,
                    investigation_status,
                    analyst_notes
                )
                VALUES (
                    :test_id,
                    :exception_type,
                    :severity,
                    'OPEN',
                    :analyst_notes
                )
            """),
            {
                "test_id": test_id,
                "exception_type": control_id,
                "severity": severity,
                "analyst_notes": (
                    "Automatically detected by InsureGuard. "
                    "Requires analyst investigation."
                )
            }
        )


# --------------------------------------------------
# EXECUTE CT-001
# --------------------------------------------------

def run_ct001(connection, run_id):

    print("\nExecuting CT-001: Payment Authorization Verification")

    records = get_authorization_results(connection)

    passed = 0
    failed = 0

    for payment in records:

        valid_approval = (
            payment["approval_id"] is not None
            and payment["approval_status"] == "APPROVED"
        )

        result = "PASS" if valid_approval else "FAIL"

        evidence = {
            "payment_id": payment["payment_id"],
            "claim_id": payment["claim_id"],
            "approval_id": payment["approval_id"],
            "approval_status": payment["approval_status"],
            "payment_amount": float(payment["payment_amount"]),
            "payment_status": payment["payment_status"]
        }

        save_test_result(
            connection=connection,
            run_id=run_id,
            control_id="CT-001",
            claim_id=payment["claim_id"],
            payment_id=payment["payment_id"],
            result=result,
            evidence=evidence,
            severity="CRITICAL"
        )

        if result == "PASS":
            passed += 1
        else:
            failed += 1

    print("Total tested:", len(records))
    print("Passed:", passed)
    print("Failed:", failed)

    return passed, failed


# --------------------------------------------------
# EXECUTE CT-002
# --------------------------------------------------

def run_ct002(connection, run_id):

    print("\nExecuting CT-002: Duplicate Payment Detection")

    records = get_duplicate_results(connection)

    passed = 0
    failed = 0

    for payment in records:

        is_duplicate = payment["duplicate_number"] > 1

        result = "FAIL" if is_duplicate else "PASS"

        evidence = {
            "payment_id": payment["payment_id"],
            "claim_id": payment["claim_id"],
            "payment_reference": payment["payment_reference"],
            "payment_amount": float(payment["payment_amount"]),
            "payment_status": payment["payment_status"],
            "duplicate_number": payment["duplicate_number"]
        }

        save_test_result(
            connection=connection,
            run_id=run_id,
            control_id="CT-002",
            claim_id=payment["claim_id"],
            payment_id=payment["payment_id"],
            result=result,
            evidence=evidence,
            severity="HIGH"
        )

        if result == "PASS":
            passed += 1
        else:
            failed += 1

    print("Total tested:", len(records))
    print("Passed:", passed)
    print("Failed:", failed)

    return passed, failed


# --------------------------------------------------
# MAIN EXECUTION
# --------------------------------------------------

def main():

    print("\n======================================")
    print(" INSUREGUARD CONTROL TESTING ENGINE")
    print("======================================")

    try:

        with engine.begin() as connection:

            run_id = create_test_run(connection)

            print("\nTest Run ID:", run_id)

            ct001 = run_ct001(connection, run_id)

            ct002 = run_ct002(connection, run_id)

            connection.execute(
                text("""
                    UPDATE insureguard.control_test_runs
                    SET run_status = 'COMPLETED'
                    WHERE run_id = :run_id
                """),
                {"run_id": run_id}
            )

        print("\n======================================")
        print(" CONTROL TESTING COMPLETED")
        print("======================================")

        print("Run ID:", run_id)

        print("\nFINAL SUMMARY")

        print(
            "CT-001 | PASS:", ct001[0],
            "| FAIL:", ct001[1]
        )

        print(
            "CT-002 | PASS:", ct002[0],
            "| FAIL:", ct002[1]
        )

        print(
            "\nExceptions created:",
            ct001[1] + ct002[1]
        )

    except Exception as error:

        print("\nCONTROL TESTING FAILED")
        print("Reason:", error)

        print(
            "The current database transaction was rolled back."
        )

        raise


if __name__ == "__main__":
    main()
