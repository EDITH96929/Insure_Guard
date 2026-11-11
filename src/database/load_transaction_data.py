from pathlib import Path

import pandas as pd
from sqlalchemy import text

from connection import engine

# ==================================================
# 1. PROJECT CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"

SCHEMA = "insureguard"

# Import order matters because of foreign keys.
DATASETS = [
    ("departments.csv", "departments"),
    ("roles.csv", "roles"),
    ("customers.csv", "customers"),
    ("employees.csv", "employees"),
    ("policies.csv", "policies"),
    ("claims.csv", "claims"),
    ("claim_approvals.csv", "claim_approvals"),
    ("payments.csv", "payments"),
]

BATCH_SIZE = 1000


# ==================================================
# 2. CLEAN CSV VALUES
# ==================================================


def clean_value(value):

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def load_csv(filename):

    path = RAW_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(path)

    if df.empty:
        raise ValueError(f"{filename} is empty.")

    return df


# ==================================================
# 3. CHECK DESTINATION TABLES
# ==================================================


def check_tables_are_empty(connection):

    print("\nChecking destination tables...")

    for _, table in DATASETS:

        count = connection.execute(
            text(f"SELECT COUNT(*) FROM {SCHEMA}.{table}")
        ).scalar_one()

        print(f"{table}: {count} existing records")

        if count > 0:
            raise RuntimeError(
                f"Table {table} is not empty. "
                "Import stopped to prevent duplicate records."
            )


# ==================================================
# 4. IMPORT CSV DATA
# ==================================================


def import_dataset(connection, filename, table):

    df = load_csv(filename)

    columns = list(df.columns)

    # Build a parameterized INSERT statement.
    column_sql = ", ".join(columns)

    parameter_sql = ", ".join(f":{column}" for column in columns)

    insert_sql = text(f"""
        INSERT INTO {SCHEMA}.{table}
        ({column_sql})
        VALUES ({parameter_sql})
        """)

    records = [
        {column: clean_value(value) for column, value in record.items()}
        for record in df.to_dict(orient="records")
    ]

    print(f"\nImporting {filename} into {table}...")

    # Insert in batches.
    for start in range(0, len(records), BATCH_SIZE):

        batch = records[start : start + BATCH_SIZE]

        connection.execute(insert_sql, batch)

    database_count = connection.execute(
        text(f"SELECT COUNT(*) FROM {SCHEMA}.{table}")
    ).scalar_one()

    if database_count != len(df):
        raise RuntimeError(
            f"Count mismatch in {table}: " f"CSV={len(df)}, Database={database_count}"
        )

    print(f"SUCCESS: {database_count:,} records imported.")


# ==================================================
# 5. SYNCHRONIZE SERIAL ID SEQUENCES
# ==================================================


def synchronize_sequences(connection):

    print("\nSynchronizing PostgreSQL ID sequences...")

    for table, column in [
        ("departments", "department_id"),
        ("roles", "role_id"),
    ]:

        connection.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence(
                        '{SCHEMA}.{table}',
                        '{column}'
                    ),
                    (SELECT MAX({column}) FROM {SCHEMA}.{table}),
                    true
                )
                """))

        print(f"{table}.{column}: synchronized")


# ==================================================
# 6. MAIN IMPORT PROCESS
# ==================================================


def main():

    print("\n======================================")
    print(" INSUREGUARD DATABASE IMPORT")
    print("======================================")

    try:

        # engine.begin() automatically commits on success
        # and rolls back if any operation fails.
        with engine.begin() as connection:

            check_tables_are_empty(connection)

            for filename, table in DATASETS:

                import_dataset(connection, filename, table)

            synchronize_sequences(connection)

        print("\n======================================")
        print(" DATABASE IMPORT SUCCESSFUL")
        print("======================================")

    except Exception as error:

        print("\n======================================")
        print(" DATABASE IMPORT FAILED")
        print("======================================")

        print(error)

        print(
            "\nAny changes made during this import "
            "transaction have been rolled back."
        )

        raise


if __name__ == "__main__":
    main()
