
from pathlib import Path
from datetime import datetime, date, time, timedelta, timezone

import numpy as np
import pandas as pd


# ==================================================
# 1. CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"

RAW_DIR.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(42)

TODAY = date(2026, 11, 11)
NUMBER_OF_CLAIMS = 5000


# ==================================================
# 2. LOAD EXISTING MASTER DATA
# ==================================================

def load_csv(filename):
    path = RAW_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    return pd.read_csv(path)


policies = load_csv("policies.csv")
employees = load_csv("employees.csv")
roles = load_csv("roles.csv")


# Convert data types
policies["start_date"] = pd.to_datetime(
    policies["start_date"], errors="coerce"
).dt.date

policies["end_date"] = pd.to_datetime(
    policies["end_date"], errors="coerce"
).dt.date

policies["coverage_limit"] = pd.to_numeric(
    policies["coverage_limit"], errors="coerce"
)

roles["approval_limit"] = pd.to_numeric(
    roles["approval_limit"], errors="coerce"
)


# Attach approval limits to employees
employees = employees.merge(
    roles[["role_id", "approval_limit"]],
    on="role_id",
    how="left"
)

employees = employees[
    employees["employee_status"] == "ACTIVE"
].copy()


if employees.empty:
    raise ValueError("No active employees found.")

if employees["approval_limit"].isna().any():
    raise ValueError("Employee approval limits are missing.")


# Select eligible insurance policies
eligible_policies = policies[
    policies["start_date"].notna()
    & policies["end_date"].notna()
    & policies["coverage_limit"].notna()
    & (policies["start_date"] <= TODAY)
    & (policies["end_date"] >= policies["start_date"])
    & (policies["coverage_limit"] > 0)
].copy()


if eligible_policies.empty:
    raise ValueError("No eligible insurance policies found.")


# ==================================================
# 3. HELPER FUNCTIONS
# ==================================================

def money(value):
    return round(max(float(value), 0.01), 2)


def random_date_between(start, end):
    days = (end - start).days

    return start + timedelta(
        days=int(RNG.integers(0, days + 1))
    )


def random_timestamp_after(claim_date):
    start = datetime.combine(
        claim_date,
        time(9, 0)
    )

    end = datetime.combine(
        TODAY,
        time(18, 0)
    )

    if end <= start:
        value = start
    else:
        seconds = int((end - start).total_seconds())

        value = start + timedelta(
            seconds=int(RNG.integers(0, seconds + 1))
        )

    return value.replace(
        tzinfo=timezone.utc
    ).isoformat()


def random_timestamp_after_timestamp(timestamp):

    start = pd.to_datetime(
        timestamp,
        utc=True
    ).to_pydatetime()

    # End of the simulation date
    cutoff = datetime.combine(
        TODAY,
        time(23, 59, 59),
        tzinfo=timezone.utc
    )

    available_seconds = int(
        (cutoff - start).total_seconds()
    )

    if available_seconds < 1:
        raise ValueError(
            "No time available for payment after approval."
        )

    # Payment must happen after approval,
    # but never beyond the simulation date.
    maximum_delay = min(
        available_seconds,
        72 * 60 * 60
    )

    delay = int(
        RNG.integers(1, maximum_delay + 1)
    )

    return (
        start + timedelta(seconds=delay)
    ).isoformat()



def choose_employee(required_limit=None, below_limit=False):

    if required_limit is None:
        pool = employees

    elif below_limit:
        pool = employees[
            employees["approval_limit"] < required_limit
        ]

    else:
        pool = employees[
            employees["approval_limit"] >= required_limit
        ]

    if pool.empty:
        pool = employees

    return pool.iloc[
        int(RNG.integers(0, len(pool)))
    ]


def choose_executor(approver_id=None):

    pool = employees

    if approver_id is not None:
        pool = employees[
            employees["employee_id"] != approver_id
        ]

    if pool.empty:
        pool = employees

    return pool.iloc[
        int(RNG.integers(0, len(pool)))
    ]


# ==================================================
# 4. GENERATE CLAIMS
# ==================================================

selected_policies = eligible_policies.sample(
    n=NUMBER_OF_CLAIMS,
    replace=len(eligible_policies) < NUMBER_OF_CLAIMS,
    random_state=42
).reset_index(drop=True)


claims = []
claim_dates = {}

claim_types = [
    "MOTOR_ACCIDENT",
    "VEHICLE_DAMAGE",
    "PROPERTY_DAMAGE",
    "FIRE_DAMAGE",
    "THEFT"
]


for i, policy in selected_policies.iterrows():

    claim_id = f"CLM{i + 1:06d}"

    claim_date = random_date_between(
        policy["start_date"],
        min(policy["end_date"], TODAY)
    )

    coverage = float(policy["coverage_limit"])

    maximum_request = min(coverage, 500000)

    requested_amount = money(
        RNG.uniform(
            min(5000, maximum_request * 0.5),
            maximum_request
        )
    )

    outcome = RNG.choice(
        ["APPROVED", "PENDING", "REJECTED"],
        p=[0.85, 0.08, 0.07]
    )

    if outcome == "PENDING":
        claim_status = "UNDER_REVIEW"

    elif outcome == "REJECTED":
        claim_status = "REJECTED"

    else:
        claim_status = "APPROVED"

    claims.append({
        "claim_id": claim_id,
        "policy_id": policy["policy_id"],
        "claim_date": claim_date.isoformat(),
        "claim_type": RNG.choice(claim_types),
        "requested_amount": requested_amount,
        "claim_status": claim_status
    })

    claim_dates[claim_id] = claim_date


claims_df = pd.DataFrame(claims)


# ==================================================
# 5. CREATE CONTROL EXCEPTION GROUPS
# ==================================================

approved_claim_ids = claims_df.loc[
    claims_df["claim_status"] == "APPROVED",
    "claim_id"
].tolist()

RNG.shuffle(approved_claim_ids)

group_size = max(
    1,
    int(len(approved_claim_ids) * 0.02)
)

missing_approval_ids = set(
    approved_claim_ids[:group_size]
)

authority_breach_ids = set(
    approved_claim_ids[group_size:group_size * 2]
)

overpayment_ids = set(
    approved_claim_ids[group_size * 2:group_size * 3]
)

duplicate_payment_ids = set(
    approved_claim_ids[group_size * 3:group_size * 4]
)


# ==================================================
# 6. GENERATE CLAIM APPROVALS
# ==================================================

approvals = []
approval_lookup = {}
ground_truth = []


for _, claim in claims_df.iterrows():

    claim_id = claim["claim_id"]
    claim_status = claim["claim_status"]

    # Intentionally create missing approval scenarios
    if claim_id in missing_approval_ids:

        ground_truth.append({
            "exception_type": "MISSING_APPROVAL",
            "record_id": claim_id,
            "description": (
                "Approved claim has a payment but no approval record."
            )
        })

        continue

    requested = float(claim["requested_amount"])

    if claim_status == "APPROVED":

        approved_amount = money(
            requested * RNG.uniform(0.80, 1.00)
        )

        approved_amount = min(
            approved_amount,
            requested
        )

    else:
        approved_amount = None

    # Intentionally create approval authority violations
    if claim_id in authority_breach_ids:

        approver = choose_employee(
            required_limit=approved_amount,
            below_limit=True
        )

        ground_truth.append({
            "exception_type": "APPROVAL_LIMIT_BREACH",
            "record_id": claim_id,
            "description": (
                "Approver's authority limit is below the approved amount."
            )
        })

    elif claim_status == "APPROVED":

        approver = choose_employee(
            required_limit=approved_amount
        )

    else:
        approver = choose_employee()

    approval_id = f"APR{len(approvals) + 1:06d}"

    if claim_status == "APPROVED":
        approval_status = "APPROVED"

    elif claim_status == "REJECTED":
        approval_status = "REJECTED"

    else:
        approval_status = "PENDING"

    approval = {
        "approval_id": approval_id,
        "claim_id": claim_id,
        "approver_id": approver["employee_id"],
        "approval_status": approval_status,
        "approved_amount": approved_amount,
        "approval_timestamp": random_timestamp_after(
            claim_dates[claim_id]
        ),
        "approval_reference": f"AUTH-{approval_id}"
    }

    approvals.append(approval)

    approval_lookup[claim_id] = approval


approvals_df = pd.DataFrame(approvals)


# ==================================================
# 7. GENERATE PAYMENTS
# ==================================================

payments = []


for _, claim in claims_df.iterrows():

    claim_id = claim["claim_id"]

    # Only approved claims can generate payments
    if claim["claim_status"] != "APPROVED":
        continue

    approval = approval_lookup.get(claim_id)

    if approval is not None:

        approved_amount = float(
            approval["approved_amount"]
        )

    else:

        # Missing approval exception
        approved_amount = (
            float(claim["requested_amount"]) * 0.90
        )

    # Create overpayment scenarios
    if claim_id in overpayment_ids:

        total_payment = money(
            approved_amount * 1.15
        )

        ground_truth.append({
            "exception_type": "OVERPAYMENT",
            "record_id": claim_id,
            "description": (
                "Total payment exceeds approved amount."
            )
        })

    else:

        total_payment = approved_amount

    # Some claims receive partial payments
    number_of_payments = (
        2 if RNG.random() < 0.15 else 1
    )

    if number_of_payments == 2:

        first_amount = money(
            total_payment * RNG.uniform(0.30, 0.70)
        )

        amounts = [
            first_amount,
            money(total_payment - first_amount)
        ]

    else:

        amounts = [money(total_payment)]

    payment_reference = f"PAYREF-{claim_id}"

    for payment_index, amount in enumerate(amounts):

        payment_id = f"PAY{len(payments) + 1:06d}"

        if claim_id in overpayment_ids:
            payment_status = "SUCCESSFUL"
        else:
            payment_status = (
                "REVERSED" if RNG.random() < 0.015
                else "SUCCESSFUL"
            )

        if approval is not None:

            payment_date = random_timestamp_after_timestamp(
                approval["approval_timestamp"]
            )

            executor = choose_executor(
                approval["approver_id"]
            )

        else:

            payment_date = random_timestamp_after(
                claim_dates[claim_id]
            )

            executor = choose_employee()

        payment = {
            "payment_id": payment_id,
            "claim_id": claim_id,
            "approval_id": (
                approval["approval_id"]
                if approval is not None
                else None
            ),
            "payment_reference": payment_reference,
            "payment_amount": amount,
            "payment_date": payment_date,
            "payment_status": payment_status,
            "executed_by": executor["employee_id"]
        }

        payments.append(payment)

        # Intentionally create an exact duplicate payment
        if (
            claim_id in duplicate_payment_ids
            and payment_index == 0
        ):

            duplicate = payment.copy()

            duplicate["payment_id"] = (
                f"PAY{len(payments) + 1:06d}"
            )

            payments.append(duplicate)

            ground_truth.append({
                "exception_type": "DUPLICATE_PAYMENT",
                "record_id": duplicate["payment_id"],
                "description": (
                    "Duplicate claim, payment reference and amount."
                )
            })


payments_df = pd.DataFrame(payments)


# ==================================================
# 8. UPDATE CLAIM SETTLEMENT STATUS
# ==================================================

successful_totals = (
    payments_df[
        payments_df["payment_status"] == "SUCCESSFUL"
    ]
    .groupby("claim_id")["payment_amount"]
    .sum()
    .to_dict()
)


for index, claim in claims_df.iterrows():

    if claim["claim_status"] != "APPROVED":
        continue

    approval = approval_lookup.get(
        claim["claim_id"]
    )

    expected_amount = (
        float(approval["approved_amount"])
        if approval is not None
        else float(claim["requested_amount"]) * 0.90
    )

    if successful_totals.get(
        claim["claim_id"], 0
    ) >= expected_amount:

        claims_df.loc[
            index, "claim_status"
        ] = "SETTLED"


# ==================================================
# 9. SAVE CSV FILES
# ==================================================

claims_df.to_csv(
    RAW_DIR / "claims.csv",
    index=False
)

approvals_df.to_csv(
    RAW_DIR / "claim_approvals.csv",
    index=False
)

payments_df.to_csv(
    RAW_DIR / "payments.csv",
    index=False
)

ground_truth_df = pd.DataFrame(
    ground_truth
)

ground_truth_df.to_csv(
    RAW_DIR / "ground_truth_exceptions.csv",
    index=False
)


# ==================================================
# 10. DATA VALIDATION
# ==================================================

print("\n========================================")
print(" INSUREGUARD TRANSACTION DATA GENERATED")
print("========================================")

for name, df in [
    ("Claims", claims_df),
    ("Approvals", approvals_df),
    ("Payments", payments_df),
    ("Ground truth exceptions", ground_truth_df)
]:

    print(f"{name:<25}: {len(df):,} records")


print("\nCLAIM STATUS DISTRIBUTION")
print(claims_df["claim_status"].value_counts())


print("\nPAYMENT STATUS DISTRIBUTION")

if not payments_df.empty:
    print(payments_df["payment_status"].value_counts())


print("\nGROUND TRUTH EXCEPTION DISTRIBUTION")

if not ground_truth_df.empty:
    print(ground_truth_df["exception_type"].value_counts())


print("\nBASIC DATA QUALITY CHECKS")

print(
    "Duplicate claim IDs:",
    claims_df["claim_id"].duplicated().sum()
)

print(
    "Duplicate approval IDs:",
    approvals_df["approval_id"].duplicated().sum()
)

print(
    "Duplicate payment IDs:",
    payments_df["payment_id"].duplicated().sum()
)

print(
    "Claims without matching policies:",
    (~claims_df["policy_id"].isin(policies["policy_id"])).sum()
)

print(
    "Payments without matching claims:",
    (~payments_df["claim_id"].isin(claims_df["claim_id"])).sum()
)

print(
    "Approvals without matching claims:",
    (~approvals_df["claim_id"].isin(claims_df["claim_id"])).sum()
)

print("\nFiles saved successfully in:")
print(RAW_DIR)
