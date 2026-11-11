
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"

claims = pd.read_csv(RAW_DIR / "claims.csv")
approvals = pd.read_csv(RAW_DIR / "claim_approvals.csv")
payments = pd.read_csv(RAW_DIR / "payments.csv")
truth = pd.read_csv(RAW_DIR / "ground_truth_exceptions.csv")
policies = pd.read_csv(RAW_DIR / "policies.csv")
employees = pd.read_csv(RAW_DIR / "employees.csv")
roles = pd.read_csv(RAW_DIR / "roles.csv")

# Prepare lookup data
employee_roles = employees.merge(
    roles[["role_id", "approval_limit"]],
    on="role_id",
    how="left"
)

approval_limits = employee_roles.set_index(
    "employee_id"
)["approval_limit"]

claim_status = claims.set_index(
    "claim_id"
)["claim_status"]

approval_by_claim = approvals.set_index(
    "claim_id"
)

# --------------------------------------------------
# 1. BASIC DATA QUALITY
# --------------------------------------------------

print("\n========== BASIC DATA QUALITY ==========")

checks = {
    "Duplicate claim IDs": claims["claim_id"].duplicated().sum(),
    "Duplicate approval IDs": approvals["approval_id"].duplicated().sum(),
    "Duplicate payment IDs": payments["payment_id"].duplicated().sum(),
    "Claims without policies": (~claims["policy_id"].isin(policies["policy_id"])).sum(),
    "Approvals without claims": (~approvals["claim_id"].isin(claims["claim_id"])).sum(),
    "Payments without claims": (~payments["claim_id"].isin(claims["claim_id"])).sum(),
    "Payments without approvals": (
        payments["approval_id"].notna()
        & ~payments["approval_id"].isin(approvals["approval_id"])
    ).sum()
}

for name, result in checks.items():
    print(f"{name}: {result}")

# --------------------------------------------------
# 2. APPROVAL AUTHORITY VALIDATION
# --------------------------------------------------

print("\n========== APPROVAL AUTHORITY ==========")

approved_records = approvals[
    approvals["approval_status"] == "APPROVED"
].copy()

approved_records["authority_limit"] = (
    approved_records["approver_id"].map(approval_limits)
)

authority_breaches = approved_records[
    approved_records["approved_amount"]
    > approved_records["authority_limit"]
]

print("Approvals exceeding employee authority:", len(authority_breaches))

# --------------------------------------------------
# 3. PAYMENT APPROVAL VALIDATION
# --------------------------------------------------

print("\n========== PAYMENT APPROVAL ==========")

payments_with_approval = payments[
    payments["approval_id"].notna()
].merge(
    approvals[
        ["approval_id", "approval_status", "approval_timestamp"]
    ],
    on="approval_id",
    how="left"
)

invalid_approval_payments = payments_with_approval[
    payments_with_approval["approval_status"] != "APPROVED"
]

missing_approval_payments = payments[
    payments["approval_id"].isna()
]

print("Payments linked to non-approved approvals:", len(invalid_approval_payments))
print("Payments without approval references:", len(missing_approval_payments))

# --------------------------------------------------
# 4. SEGREGATION OF DUTIES
# --------------------------------------------------

print("\n========== SEGREGATION OF DUTIES ==========")

sod = payments.merge(
    approvals[["approval_id", "approver_id"]],
    on="approval_id",
    how="inner"
)

sod_breaches = sod[
    sod["executed_by"] == sod["approver_id"]
]

print("Payments executed by their approver:", len(sod_breaches))

# --------------------------------------------------
# 5. PAYMENT TIMING
# --------------------------------------------------

print("\n========== PAYMENT TIMING ==========")

timing = payments_with_approval.copy()

timing["payment_date"] = pd.to_datetime(
    timing["payment_date"], utc=True
)

timing["approval_timestamp"] = pd.to_datetime(
    timing["approval_timestamp"], utc=True
)

payments_before_approval = timing[
    timing["payment_date"] <= timing["approval_timestamp"]
]

simulation_cutoff = pd.Timestamp(
    "2026-11-11T23:59:59Z"
)

future_payments = payments[
    pd.to_datetime(payments["payment_date"], utc=True)
    > simulation_cutoff
]

print("Payments made before or at approval time:", len(payments_before_approval))
print("Payments dated in the future:", len(future_payments))

# --------------------------------------------------
# 6. OVERPAYMENT VALIDATION
# --------------------------------------------------


# --------------------------------------------------
# 6. OVERPAYMENT VALIDATION
# --------------------------------------------------

print("\n========== OVERPAYMENT ==========")

# Only successful payments count toward settled amounts.
successful_payments = payments[
    payments["payment_status"] == "SUCCESSFUL"
].copy()

# Remove exact duplicate transaction records for this
# calculation. We test duplicate payments separately.
successful_payments = successful_payments.drop_duplicates(
    subset=[
        "claim_id",
        "payment_reference",
        "payment_amount",
        "payment_status"
    ],
    keep="first"
)

# Aggregate successful, non-duplicate payments.
paid_totals = (
    successful_payments
    .groupby("claim_id")["payment_amount"]
    .sum()
)

# Only claims with an actual approved amount can be
# tested for overpayment.
approved_amounts = approvals[
    approvals["approval_status"] == "APPROVED"
].set_index("claim_id")["approved_amount"]

comparison = pd.concat(
    [
        paid_totals.rename("paid_amount"),
        approved_amounts.rename("approved_amount")
    ],
    axis=1
)

# Exclude claims without approval records.
comparison = comparison.dropna(
    subset=["approved_amount"]
)

# Small rounding tolerance for currency calculations.
overpayments = comparison[
    comparison["paid_amount"]
    > comparison["approved_amount"] + 0.01
]

print(
    "Claims with successful payments above approval:",
    len(overpayments)
)

print(
    "Total excess payment amount:",
    round(
        (
            overpayments["paid_amount"]
            - overpayments["approved_amount"]
        ).sum(),
        2
    )
)


# --------------------------------------------------
# 7. DUPLICATE PAYMENT VALIDATION
# --------------------------------------------------

print("\n========== DUPLICATE PAYMENTS ==========")

duplicates = payments[
    payments.duplicated(
        subset=[
            "claim_id",
            "payment_reference",
            "payment_amount",
            "payment_status"
        ],
        keep=False
    )
]

print("Rows involved in potential duplicate payments:", len(duplicates))

# --------------------------------------------------
# 8. GROUND TRUTH SUMMARY
# --------------------------------------------------

print("\n========== GROUND TRUTH ==========")

print(truth["exception_type"].value_counts())

print("\nTotal ground truth exception records:", len(truth))

# --------------------------------------------------
# 9. FINAL SUMMARY
# --------------------------------------------------

print("\n========== VALIDATION COMPLETED ==========")
print("Claims:", len(claims))
print("Approvals:", len(approvals))
print("Payments:", len(payments))
print("Ground truth records:", len(truth))

print("\nReview all findings before database import.")
