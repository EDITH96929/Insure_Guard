
"""
InsureGuard - Risk Intelligence Engine

Connects:
    Risk Register
    Risk-Control Mapping
    Control Library
    Control Tests
    Exceptions

Purpose:
    Provide risk-level visibility into control failures
    and the underlying claims and payment references.

This version analyzes the latest completed control test run.
"""

import sys
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
# SQL: FIND LATEST COMPLETED RUN
# --------------------------------------------------

LATEST_RUN_QUERY = text("""
    SELECT MAX(run_id)
    FROM insureguard.control_test_runs
    WHERE run_status = 'COMPLETED'
""")


# --------------------------------------------------
# SQL: RISK-LEVEL SUMMARY
# --------------------------------------------------

RISK_SUMMARY_QUERY = text("""
    SELECT
        r.risk_id,
        r.risk_name,
        r.inherent_score,

        cl.control_id,
        cl.control_name,

        COUNT(DISTINCT e.exception_id) AS total_exceptions,

        COUNT(DISTINCT e.exception_id)
            FILTER (
                WHERE e.investigation_status = 'OPEN'
            ) AS open_exceptions,

        COUNT(DISTINCT e.exception_id)
            FILTER (
                WHERE e.investigation_status <> 'OPEN'
            ) AS other_status_exceptions,

        COUNT(DISTINCT ct.claim_id) AS affected_claims,

        COUNT(DISTINCT ct.payment_id) AS affected_payments

    FROM insureguard.risk_register r

    JOIN insureguard.risk_control_mapping m
        ON r.risk_id = m.risk_id

    JOIN insureguard.control_library cl
        ON m.control_id = cl.control_id

    LEFT JOIN insureguard.control_tests ct
        ON cl.control_id = ct.control_id
        AND ct.run_id = :run_id
        AND ct.test_result = 'FAIL'

    LEFT JOIN insureguard.exceptions e
        ON ct.test_id = e.test_id

    GROUP BY
        r.risk_id,
        r.risk_name,
        r.inherent_score,
        cl.control_id,
        cl.control_name

    ORDER BY
        r.inherent_score DESC,
        r.risk_id
""")


# --------------------------------------------------
# SQL: EXCEPTION DETAILS
# --------------------------------------------------

EXCEPTION_DETAILS_QUERY = text("""
    SELECT
        r.risk_id,
        r.risk_name,

        cl.control_id,
        cl.control_name,

        e.exception_id,
        e.exception_type,
        e.severity,
        e.investigation_status,
        e.analyst_notes,

        ct.claim_id,
        ct.payment_id

    FROM insureguard.risk_register r

    JOIN insureguard.risk_control_mapping m
        ON r.risk_id = m.risk_id

    JOIN insureguard.control_library cl
        ON m.control_id = cl.control_id

    JOIN insureguard.control_tests ct
        ON cl.control_id = ct.control_id

    JOIN insureguard.exceptions e
        ON ct.test_id = e.test_id

    WHERE ct.run_id = :run_id
      AND ct.test_result = 'FAIL'

    ORDER BY
        r.risk_id,
        e.severity,
        e.exception_id
""")


# --------------------------------------------------
# DISPLAY RISK SUMMARY
# --------------------------------------------------

def display_risk_summary(rows):

    print("\n" + "=" * 75)
    print("RISK INTELLIGENCE SUMMARY")
    print("=" * 75)

    if not rows:
        print("No risk records found for this testing run.")
        return

    for row in rows:

        print(f"\nRisk ID       : {row['risk_id']}")
        print(f"Risk Name     : {row['risk_name']}")
        print(f"Inherent Risk : {row['inherent_score']}/25")

        print(
            f"Control       : {row['control_id']} - "
            f"{row['control_name']}"
        )

        print(
            f"Exceptions    : {row['total_exceptions']}"
        )

        print(
            f"Open          : {row['open_exceptions']}"
        )

        print(
            f"Other Status  : {row['other_status_exceptions']}"
        )

        print(
            f"Claims        : {row['affected_claims']}"
        )

        print(
            f"Payments      : {row['affected_payments']}"
        )

        print("-" * 75)


# --------------------------------------------------
# DISPLAY EXCEPTION DETAILS
# --------------------------------------------------

def display_exception_details(rows):

    print("\n" + "=" * 75)
    print("EXCEPTION INVESTIGATION DETAILS")
    print("=" * 75)

    if not rows:
        print("No exceptions found.")
        return

    for row in rows:

        print(f"\nException ID : {row['exception_id']}")
        print(f"Risk         : {row['risk_id']} - {row['risk_name']}")

        print(
            f"Control      : {row['control_id']} - "
            f"{row['control_name']}"
        )

        print(f"Type         : {row['exception_type']}")
        print(f"Severity     : {row['severity']}")
        print(f"Status       : {row['investigation_status']}")
        print(f"Claim ID     : {row['claim_id']}")
        print(f"Payment ID   : {row['payment_id']}")
        print(f"Notes        : {row['analyst_notes']}")

        print("-" * 75)


# --------------------------------------------------
# MAIN ENGINE
# --------------------------------------------------

def run_risk_intelligence():

    print("=" * 75)
    print("             INSUREGUARD RISK INTELLIGENCE ENGINE")
    print("=" * 75)

    with engine.connect() as connection:

        run_id = connection.execute(
            LATEST_RUN_QUERY
        ).scalar_one_or_none()

        if run_id is None:
            print("No completed control testing runs found.")
            return

        print(f"\nAnalyzing Control Test Run ID: {run_id}")

        summary_rows = connection.execute(
            RISK_SUMMARY_QUERY,
            {"run_id": run_id}
        ).mappings().all()

        exception_rows = connection.execute(
            EXCEPTION_DETAILS_QUERY,
            {"run_id": run_id}
        ).mappings().all()

    display_risk_summary(summary_rows)

    display_exception_details(exception_rows)

    print("\n" + "=" * 75)
    print("RISK INTELLIGENCE ANALYSIS COMPLETED")
    print("=" * 75)

    print(f"Testing Run ID       : {run_id}")
    print(f"Risks Analyzed       : {len(summary_rows)}")
    print(f"Exceptions Retrieved : {len(exception_rows)}")

    print("Database Operation  : READ ONLY")


if __name__ == "__main__":
    run_risk_intelligence()
