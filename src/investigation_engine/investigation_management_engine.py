
import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect, text

# Make the src folder importable
SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_DIR))

from database.connection import engine


SCHEMA = "insureguard"
ADVISORY_LOCK_KEY = 20261112


def get_table_columns(table_name):
    """Return the column names for a table."""
    inspector = inspect(engine)

    if not inspector.has_table(table_name, schema=SCHEMA):
        raise RuntimeError(
            f"Required table '{SCHEMA}.{table_name}' was not found."
        )

    return {
        column["name"]
        for column in inspector.get_columns(table_name, schema=SCHEMA)
    }


def get_active_employees(connection):
    """
    Find active employees using the available status column.
    Fail safely if the database does not expose an active-status field.
    """
    columns = get_table_columns("employees")

    if "employee_id" not in columns:
        raise RuntimeError("employees.employee_id column was not found.")

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

        if status_column is None:
            raise RuntimeError(
                "Could not identify the employee active-status column. "
                "Expected is_active, employment_status, "
                "employee_status, or status."
            )

        # Column name comes only from the fixed allowlist above.
        query = text(f"""
            SELECT employee_id
            FROM insureguard.employees
            WHERE UPPER({status_column}) = 'ACTIVE'
            ORDER BY employee_id
        """)

    employees = connection.execute(query).scalars().all()

    if not employees:
        raise RuntimeError("No active employees were found.")

    return employees


def get_latest_run_id(connection):
    """Get the latest control test run."""
    run_id = connection.execute(text("""
        SELECT MAX(run_id)
        FROM insureguard.control_test_runs
    """)).scalar_one_or_none()

    if run_id is None:
        raise RuntimeError(
            "No control test runs were found. Run the control engine first."
        )

    return run_id


def get_exceptions_for_run(connection, run_id):
    """
    Retrieve exceptions associated with the selected control test run.
    The relationship is exceptions.test_id -> control_tests.test_id.
    """
    exception_columns = get_table_columns("exceptions")
    test_columns = get_table_columns("control_tests")

    required_exception_columns = {"exception_id", "test_id"}
    required_test_columns = {"test_id", "run_id"}

    if not required_exception_columns.issubset(exception_columns):
        raise RuntimeError(
            "The exceptions table is missing exception_id or test_id."
        )

    if not required_test_columns.issubset(test_columns):
        raise RuntimeError(
            "The control_tests table is missing test_id or run_id."
        )

    return connection.execute(
        text("""
            SELECT DISTINCT e.exception_id
            FROM insureguard.exceptions AS e
            INNER JOIN insureguard.control_tests AS ct
                ON ct.test_id = e.test_id
            WHERE ct.run_id = :run_id
            ORDER BY e.exception_id
        """),
        {"run_id": run_id}
    ).scalars().all()


def create_investigation_cases(apply_changes=False):
    """Create one OPEN investigation case for each exception without one."""

    with engine.begin() as connection:

        # Prevent two executions from assigning the same exceptions together.
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": ADVISORY_LOCK_KEY}
        )

        run_id = get_latest_run_id(connection)
        exception_ids = get_exceptions_for_run(connection, run_id)
        employees = get_active_employees(connection)

        existing_ids = set(
            connection.execute(text("""
                SELECT DISTINCT exception_id
                FROM insureguard.investigation_records
            """)).scalars().all()
        )

        missing_ids = [
            exception_id
            for exception_id in exception_ids
            if exception_id not in existing_ids
        ]

        print("\nINSUREGUARD — INVESTIGATION CASE SETUP")
        print("-" * 48)
        print(f"Latest control test run : {run_id}")
        print(f"Exceptions found        : {len(exception_ids)}")
        print(f"Existing cases          : {len(existing_ids)}")
        print(f"New cases to create     : {len(missing_ids)}")
        print(f"Active investigators    : {len(employees)}")

        if not missing_ids:
            print("\nNo new investigation cases are required.")
            return

        if not apply_changes:
            print("\nPREVIEW ONLY — no database records were inserted.")
            print("Review the numbers above, then run with --apply.")
            return

        records = []

        for index, exception_id in enumerate(missing_ids):
            investigator_id = employees[index % len(employees)]

            records.append({
                "exception_id": exception_id,
                "investigator_id": investigator_id,
            })

        connection.execute(
            text("""
                INSERT INTO insureguard.investigation_records (
                    exception_id,
                    investigator_id,
                    investigation_status
                )
                VALUES (
                    :exception_id,
                    :investigator_id,
                    'OPEN'
                )
            """),
            records
        )

        print("\nDATABASE CHANGES COMMITTED")
        print(f"Investigation cases created: {len(records)}")
        print("Initial investigation status: OPEN")

        print(
            "\nNote: Investigator assignment is round-robin "
            "for this synthetic demonstration. "
            "A real organisation would assign cases based on "
            "workload, expertise, independence and authority."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create InsureGuard investigation cases."
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert investigation cases into PostgreSQL."
    )

    args = parser.parse_args()

    try:
        create_investigation_cases(apply_changes=args.apply)

    except Exception as error:
        print("\nInvestigation engine failed:")
        print(error)
        raise
