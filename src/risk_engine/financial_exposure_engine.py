
"""
InsureGuard - Financial Exposure Analysis Engine

Analyzes potential financial exposure for:
    RISK-001: Unauthorized Claim Payments
    RISK-002: Duplicate Payment Exposure
    RISK-003: Incorrect Settlement Amounts

Important:
    Exposure is not the same as confirmed financial loss.
    Only successful payments are quantified.
    Reversed and failed payments are excluded.
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
# FIND LATEST COMPLETED CONTROL TEST RUN
# --------------------------------------------------

LATEST_RUN_QUERY = text("""
    SELECT MAX(run_id)
    FROM insureguard.control_test_runs
    WHERE run_status = 'COMPLETED'
""")


# --------------------------------------------------
# CT-001: UNAUTHORIZED PAYMENT EXPOSURE
# --------------------------------------------------

UNAUTHORIZED_PAYMENT_QUERY = text("""
    WITH flagged_payments AS (
        SELECT DISTINCT
            p.payment_id,
            p.approval_id,
            p.payment_amount,
            p.payment_status,
            p.payment_reference
        FROM insureguard.exceptions e
        JOIN insureguard.control_tests ct
            ON e.test_id = ct.test_id
        JOIN insureguard.payments p
            ON ct.payment_id = p.payment_id
        WHERE ct.run_id = :run_id
          AND ct.control_id = 'CT-001'
          AND ct.test_result = 'FAIL'
    )

    SELECT
        COUNT(*) AS flagged_payments,

        COUNT(*) FILTER (
            WHERE payment_status = 'SUCCESSFUL'
        ) AS successful_payments,

        COALESCE(
            SUM(payment_amount) FILTER (
                WHERE payment_status = 'SUCCESSFUL'
            ),
            0
        ) AS potential_exposure

    FROM flagged_payments
""")


# --------------------------------------------------
# CT-002: DUPLICATE PAYMENT EXPOSURE
# --------------------------------------------------

DUPLICATE_PAYMENT_QUERY = text("""
    WITH flagged_payments AS (
        SELECT DISTINCT
            p.payment_id,
            p.payment_reference,
            p.payment_amount,
            p.payment_status
        FROM insureguard.exceptions e
        JOIN insureguard.control_tests ct
            ON e.test_id = ct.test_id
        JOIN insureguard.payments p
            ON ct.payment_id = p.payment_id
        WHERE ct.run_id = :run_id
          AND ct.control_id = 'CT-002'
          AND ct.test_result = 'FAIL'
    )

    SELECT
        COUNT(*) AS flagged_payments,

        COUNT(*) FILTER (
            WHERE payment_status = 'SUCCESSFUL'
              AND payment_reference IS NOT NULL
        ) AS quantifiable_duplicate_payments,

        COUNT(*) FILTER (
            WHERE payment_status = 'SUCCESSFUL'
              AND payment_reference IS NULL
        ) AS missing_reference_payments,

        COALESCE(
            SUM(payment_amount) FILTER (
                WHERE payment_status = 'SUCCESSFUL'
                  AND payment_reference IS NOT NULL
            ),
            0
        ) AS potential_exposure

    FROM flagged_payments
""")


# --------------------------------------------------
# CT-003: SETTLEMENT OVERPAYMENT EXPOSURE
# --------------------------------------------------

OVERPAYMENT_QUERY = text("""
    WITH flagged_claims AS (
        SELECT DISTINCT
            ct.claim_id
        FROM insureguard.exceptions e
        JOIN insureguard.control_tests ct
            ON e.test_id = ct.test_id
        WHERE ct.run_id = :run_id
          AND ct.control_id = 'CT-003'
          AND ct.test_result = 'FAIL'
          AND ct.claim_id IS NOT NULL
    ),

    ranked_approvals AS (
        SELECT
            claim_id,
            approved_amount,

            ROW_NUMBER() OVER (
                PARTITION BY claim_id
                ORDER BY approval_timestamp DESC, approval_id DESC
            ) AS approval_rank

        FROM insureguard.claim_approvals

        WHERE approval_status = 'APPROVED'
          AND approved_amount IS NOT NULL
    ),

    deduplicated_payments AS (
        SELECT
            payment_id,
            claim_id,
            payment_amount,
            payment_status,

            ROW_NUMBER() OVER (
                PARTITION BY
                    claim_id,
                    CASE
                        WHEN payment_reference IS NULL
                            THEN 'PAYMENT:' || payment_id
                        ELSE 'REFERENCE:' || payment_reference
                    END,
                    payment_amount,
                    payment_status
                ORDER BY payment_id
            ) AS duplicate_number

        FROM insureguard.payments
    ),

    payment_totals AS (
        SELECT
            claim_id,
            SUM(payment_amount) AS total_paid

        FROM deduplicated_payments

        WHERE payment_status = 'SUCCESSFUL'
          AND duplicate_number = 1

        GROUP BY claim_id
    ),

    claim_exposure AS (
        SELECT
            fc.claim_id,
            ra.approved_amount,
            COALESCE(pt.total_paid, 0) AS total_paid,

            GREATEST(
                COALESCE(pt.total_paid, 0) - ra.approved_amount,
                0
            ) AS excess_amount

        FROM flagged_claims fc

        JOIN ranked_approvals ra
            ON fc.claim_id = ra.claim_id
           AND ra.approval_rank = 1

        LEFT JOIN payment_totals pt
            ON fc.claim_id = pt.claim_id
    )

    SELECT
        COUNT(*) AS assessed_claims,

        COUNT(*) FILTER (
            WHERE excess_amount > 0
        ) AS overpaid_claims,

        COALESCE(
            SUM(excess_amount),
            0
        ) AS potential_exposure

    FROM claim_exposure
""")


# --------------------------------------------------
# DISPLAY CURRENCY
# --------------------------------------------------

def format_currency(amount):
    return f"INR {float(amount):,.2f}"


# --------------------------------------------------
# DISPLAY RESULTS
# --------------------------------------------------

def display_exposure(
    risk_id,
    risk_name,
    result,
    exposure_key="potential_exposure"
):

    print("\n" + "-" * 65)
    print(f"Risk ID       : {risk_id}")
    print(f"Risk Name     : {risk_name}")

    for key, value in result.items():

        if key == exposure_key:
            print(f"Potential Exposure : {format_currency(value)}")
        else:
            print(f"{key.replace('_', ' ').title()} : {value}")


# --------------------------------------------------
# MAIN ENGINE
# --------------------------------------------------

def run_financial_exposure_analysis():

    print("=" * 65)
    print("       INSUREGUARD FINANCIAL EXPOSURE ENGINE")
    print("=" * 65)

    with engine.connect() as connection:

        run_id = connection.execute(
            LATEST_RUN_QUERY
        ).scalar_one_or_none()

        if run_id is None:
            print("No completed control test run found.")
            return

        print(f"\nControl Test Run ID: {run_id}")

        parameters = {"run_id": run_id}

        # CT-001
        unauthorized = connection.execute(
            UNAUTHORIZED_PAYMENT_QUERY,
            parameters
        ).mappings().one()

        # CT-002
        duplicates = connection.execute(
            DUPLICATE_PAYMENT_QUERY,
            parameters
        ).mappings().one()

        # CT-003
        overpayments = connection.execute(
            OVERPAYMENT_QUERY,
            parameters
        ).mappings().one()

    # Display results
    display_exposure(
        "RISK-001",
        "Unauthorized Claim Payments",
        unauthorized
    )

    display_exposure(
        "RISK-002",
        "Duplicate Payment Exposure",
        duplicates
    )

    display_exposure(
        "RISK-003",
        "Incorrect Settlement Amounts",
        overpayments
    )

    print("\n" + "=" * 65)
    print("FINANCIAL EXPOSURE ANALYSIS COMPLETED")
    print("=" * 65)

    print(f"Control Test Run : {run_id}")
    print("Database         : READ ONLY")

    print(
        "\nIMPORTANT: These figures represent potential exposure, "
        "not confirmed financial loss."
    )

    print(
        "Exposure categories may overlap and must not be added "
        "together without reconciliation."
    )


if __name__ == "__main__":
    run_financial_exposure_analysis()
