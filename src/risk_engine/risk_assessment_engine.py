
"""
InsureGuard - Risk Assessment Engine

Purpose:
    Assess business risks associated with insurance claims
    and payment operations.

Methodology:
    Inherent Risk = Likelihood * Impact

    Residual Risk = Inherent Risk * (1 - Control Effectiveness)

Important:
    Control effectiveness and residual risk remain NULL until
    sufficient control assessment evidence is available.

Risk bands:
    1-4   : LOW
    5-9   : MODERATE
    10-15 : HIGH
    16-25 : CRITICAL
"""

import sys
from pathlib import Path

from sqlalchemy import text

# Resolve project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

from database.connection import engine


# --------------------------------------------------
# RISK CLASSIFICATION
# --------------------------------------------------

def classify_risk(score):
    if score <= 4:
        return "LOW"
    elif score <= 9:
        return "MODERATE"
    elif score <= 15:
        return "HIGH"
    return "CRITICAL"


# --------------------------------------------------
# RISK REGISTER DEFINITIONS
# --------------------------------------------------

RISKS = [
    {
        "risk_id": "RISK-001",
        "risk_name": "Unauthorized Claim Payments",
        "risk_description": (
            "Risk of insurance payments being processed without "
            "valid approval or appropriate authorization. This may "
            "result in financial loss, policy violations and "
            "regulatory or compliance issues."
        ),
        "likelihood": 4,
        "impact": 5,
        "control_effectiveness": None,
    },
    {
        "risk_id": "RISK-002",
        "risk_name": "Duplicate Payment Exposure",
        "risk_description": (
            "Risk of multiple payments being made for the same "
            "claim and payment obligation due to inadequate "
            "duplicate detection or reconciliation."
        ),
        "likelihood": 3,
        "impact": 4,
        "control_effectiveness": None,
    },
    {
        "risk_id": "RISK-003",
        "risk_name": "Incorrect Settlement Amounts",
        "risk_description": (
            "Risk of claim payments exceeding approved settlement "
            "amounts or otherwise being processed inaccurately, "
            "causing financial exposure and reporting errors."
        ),
        "likelihood": 4,
        "impact": 5,
        "control_effectiveness": None,
    },
]


# --------------------------------------------------
# RISK CALCULATION
# --------------------------------------------------

def calculate_risk(likelihood, impact, effectiveness=None):

    inherent_score = likelihood * impact

    inherent_category = classify_risk(inherent_score)

    residual_score = None

    if effectiveness is not None:
        if not 0 <= effectiveness <= 1:
            raise ValueError(
                "Control effectiveness must be between 0 and 1."
            )

        residual_score = round(
            inherent_score * (1 - effectiveness), 2
        )

    return {
        "inherent_score": inherent_score,
        "inherent_category": inherent_category,
        "residual_score": residual_score,
    }


# --------------------------------------------------
# DATABASE UPSERT
# --------------------------------------------------

UPSERT_RISK = text("""
    INSERT INTO insureguard.risk_register (
        risk_id,
        risk_name,
        risk_description,
        likelihood,
        impact,
        control_effectiveness,
        residual_score,
        risk_owner,
        risk_status
    )
    VALUES (
        :risk_id,
        :risk_name,
        :risk_description,
        :likelihood,
        :impact,
        :control_effectiveness,
        :residual_score,
        NULL,
        'ACTIVE'
    )
    ON CONFLICT (risk_id)
    DO UPDATE SET
        risk_name = EXCLUDED.risk_name,
        risk_description = EXCLUDED.risk_description,
        likelihood = EXCLUDED.likelihood,
        impact = EXCLUDED.impact,
        control_effectiveness = EXCLUDED.control_effectiveness,
        residual_score = EXCLUDED.residual_score
""")


# --------------------------------------------------
# MAIN ENGINE
# --------------------------------------------------

def run_risk_assessment():

    print("=" * 55)
    print("       INSUREGUARD RISK ASSESSMENT ENGINE")
    print("=" * 55)

    assessed_risks = []

    try:
        with engine.begin() as connection:

            for risk in RISKS:

                result = calculate_risk(
                    likelihood=risk["likelihood"],
                    impact=risk["impact"],
                    effectiveness=risk["control_effectiveness"],
                )

                risk_record = {
                    **risk,
                    **result,
                }

                connection.execute(
                    UPSERT_RISK,
                    {
                        "risk_id": risk["risk_id"],
                        "risk_name": risk["risk_name"],
                        "risk_description": risk["risk_description"],
                        "likelihood": risk["likelihood"],
                        "impact": risk["impact"],
                        "control_effectiveness": risk[
                            "control_effectiveness"
                        ],
                        "residual_score": result["residual_score"],
                    },
                )

                assessed_risks.append(risk_record)

                print(f"\nRisk ID: {risk['risk_id']}")
                print(f"Risk Name: {risk['risk_name']}")
                print(
                    f"Likelihood: {risk['likelihood']} | "
                    f"Impact: {risk['impact']}"
                )
                print(
                    f"Inherent Risk: {result['inherent_score']} "
                    f"({result['inherent_category']})"
                )

                if result["residual_score"] is None:
                    print("Residual Risk: PENDING CONTROL ASSESSMENT")

        print("\n" + "=" * 55)
        print("RISK ASSESSMENT COMPLETED SUCCESSFULLY")
        print("=" * 55)
        print(f"Total risks processed: {len(assessed_risks)}")
        print("Database transaction: COMMITTED")

    except Exception as error:
        print("\nRisk assessment failed.")
        print("Database transaction rolled back.")
        raise


if __name__ == "__main__":
    run_risk_assessment()
