
import random
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# --------------------------------------------------
# INSUREGUARD MASTER DATA GENERATOR
# Version: 1.0
# --------------------------------------------------

SEED = 42

random.seed(SEED)
np.random.seed(SEED)

fake = Faker("en_IN")
Faker.seed(SEED)

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"

RAW_DIR.mkdir(parents=True, exist_ok=True)

TODAY = date(2026, 11, 11)


def save_dataset(data, filename):
    """Save generated data as CSV."""
    df = pd.DataFrame(data)

    path = RAW_DIR / filename
    df.to_csv(path, index=False)

    print(f"Generated {filename}: {len(df)} records")

    return df


# --------------------------------------------------
# 1. DEPARTMENTS
# --------------------------------------------------

departments = [
    {"department_id": 1, "department_name": "Claims Operations"},
    {"department_id": 2, "department_name": "Finance"},
    {"department_id": 3, "department_name": "Risk and Compliance"},
    {"department_id": 4, "department_name": "Internal Audit"},
]

save_dataset(departments, "departments.csv")


# --------------------------------------------------
# 2. EMPLOYEE ROLES
# --------------------------------------------------

roles = [
    {
        "role_id": 1,
        "role_name": "Junior Claims Officer",
        "approval_limit": 25000
    },
    {
        "role_id": 2,
        "role_name": "Senior Claims Officer",
        "approval_limit": 100000
    },
    {
        "role_id": 3,
        "role_name": "Claims Manager",
        "approval_limit": 500000
    },
    {
        "role_id": 4,
        "role_name": "Department Head",
        "approval_limit": 5000000
    },
    {
        "role_id": 5,
        "role_name": "Finance Payment Officer",
        "approval_limit": 0
    }
]

save_dataset(roles, "roles.csv")


# --------------------------------------------------
# 3. EMPLOYEES
# --------------------------------------------------

employees = []

department_distribution = [1, 2, 3, 4]
role_distribution = [1, 2, 3, 4, 5]

for i in range(1, 101):

    department_id = random.choices(
        department_distribution,
        weights=[50, 25, 15, 10]
    )[0]

    # Keep role assignment aligned with department
    if department_id == 1:
        role_id = random.choices(
            [1, 2, 3, 4],
            weights=[45, 35, 15, 5]
        )[0]

    elif department_id == 2:
        role_id = random.choice([4, 5])

    else:
        role_id = random.choice([3, 4])

    employees.append({
        "employee_id": f"EMP{i:04d}",
        "employee_name": fake.name(),
        "department_id": department_id,
        "role_id": role_id,
        "employee_status": random.choices(
            ["ACTIVE", "INACTIVE"],
            weights=[95, 5]
        )[0]
    })

save_dataset(employees, "employees.csv")


# --------------------------------------------------
# 4. CUSTOMERS
# --------------------------------------------------

regions = [
    "Bengaluru",
    "Mumbai",
    "Delhi",
    "Hyderabad",
    "Chennai",
    "Pune",
    "Kolkata",
    "Bhubaneswar",
    "Jaipur",
    "Ahmedabad"
]

customers = []

for i in range(1, 8001):

    customers.append({
        "customer_id": f"CUST{i:06d}",
        "customer_name": fake.name(),
        "region": random.choice(regions)
    })

save_dataset(customers, "customers.csv")


# --------------------------------------------------
# 5. INSURANCE POLICIES
# --------------------------------------------------

policies = []

for i in range(1, 10001):

    customer_id = f"CUST{random.randint(1, 8000):06d}"

    policy_type = random.choices(
        ["MOTOR", "PROPERTY"],
        weights=[75, 25]
    )[0]

    start_date = TODAY - timedelta(
        days=random.randint(30, 1000)
    )

    end_date = start_date + timedelta(days=365)

    if end_date < TODAY:
        policy_status = "EXPIRED"
    else:
        policy_status = "ACTIVE"

    coverage_limit = random.choice(
        [250000, 500000, 1000000, 2500000, 5000000]
    )

    policies.append({
        "policy_id": f"POL{i:06d}",
        "customer_id": customer_id,
        "policy_type": policy_type,
        "coverage_limit": coverage_limit,
        "start_date": start_date,
        "end_date": end_date,
        "policy_status": policy_status
    })

save_dataset(policies, "policies.csv")


# --------------------------------------------------
# 6. BASIC DATA QUALITY CHECKS
# --------------------------------------------------

print("\nINSUREGUARD DATA QUALITY REPORT")
print("--------------------------------")

for filename in [
    "departments.csv",
    "roles.csv",
    "employees.csv",
    "customers.csv",
    "policies.csv"
]:

    df = pd.read_csv(RAW_DIR / filename)

    print(f"\nDataset: {filename}")
    print("Rows:", len(df))
    print("Duplicate rows:", df.duplicated().sum())
    print("Missing values:", df.isnull().sum().sum())

print("\nMaster data generation completed!")
